from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Course, Major, StudentProfile
from accounts.models import User


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "title", "description", "credits", "capacity", "professor"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["professor"].queryset = User.objects.filter(role="professor")
        self.fields["professor"].required = False
        self.fields["professor"].empty_label = "— Unassigned —"


class CreateUserForm(forms.Form):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("advisor", "Advisor"),
        ("registrar", "Registrar"),
    ]

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    university_id = forms.CharField(max_length=20, required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    major = forms.ModelChoiceField(
        queryset=Major.objects.select_related("advisor").all(),
        required=False,
        empty_label="— Select a major —",
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean_university_id(self):
        uid = self.cleaned_data.get("university_id")
        if uid and User.objects.filter(university_id=uid).exists():
            raise forms.ValidationError("This university ID is already taken.")
        return uid

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        major = cleaned_data.get("major")
        if role == "student" and not major:
            self.add_error("major", "A major is required for student accounts.")
        return cleaned_data

    def save(self):
        data = self.cleaned_data
        role = data["role"]
        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data.get("email", ""),
            role=role,
            university_id=data.get("university_id") or None,
        )
        major = data.get("major")
        if role == "student" and major:
            StudentProfile.objects.create(
                user=user,
                major=major.name,
                advisor=major.advisor,
            )
        elif role == "advisor" and major:
            major.advisor = user
            major.save()
        return user


# Keep old name as alias so existing imports don't break
CreateStudentForm = CreateUserForm


class EditUserForm(forms.ModelForm):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("professor", "Professor"),
        ("advisor", "Advisor"),
        ("registrar", "Registrar"),
        ("sysadmin", "Sys Admin"),
    ]

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    new_password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        label="New Password",
        help_text="Leave blank to keep current password.",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "university_id", "role"]

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean_university_id(self):
        uid = self.cleaned_data.get("university_id")
        if uid:
            qs = User.objects.filter(university_id=uid).exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This university ID is already taken.")
        return uid

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password:
            validate_password(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("new_password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class MajorForm(forms.ModelForm):
    advisor = forms.ModelChoiceField(
        queryset=User.objects.none(),  # set in __init__
        required=False,
        empty_label="— Assign later —",
    )

    class Meta:
        model = Major
        fields = ["name", "advisor"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["advisor"].queryset = User.objects.filter(role="advisor")
