from django import forms
from registration.forms import RegistrationForm
from registration.signals import user_registered

from tobaccocessation.main.choices import FACULTY_CHOICES, \
    INSTITUTION_CHOICES, GENDER_CHOICES, RACE_CHOICES, \
    HISPANIC_LATINO_CHOICES, AGE_CHOICES, SPECIALTY_CHOICES
from tobaccocessation.main.models import UserProfile


class CreateAccountForm(RegistrationForm):
    '''This is a form class that will be used
    to allow guest users to create guest accounts.'''
    first_name = forms.CharField(
        max_length=25, required=True, label="First Name")
    last_name = forms.CharField(
        max_length=25, required=True, label="Last Name")
    username = forms.CharField(
        max_length=25, required=True, label="Username")
    password1 = forms.CharField(
        max_length=25, widget=forms.PasswordInput, required=True,
        label="Password")
    password2 = forms.CharField(
        max_length=25, widget=forms.PasswordInput, required=True,
        label="Confirm Password")
    email = forms.EmailField()
    # consent = forms.(required=True)
    consent_participant = forms.BooleanField(required=False)
    consent_not_participant = forms.BooleanField(required=False)
    is_faculty = forms.ChoiceField(required=True, choices=FACULTY_CHOICES)
    institute = forms.ChoiceField(choices=INSTITUTION_CHOICES, required=True)
    gender = forms.ChoiceField(required=True, initial="-----",
                               choices=GENDER_CHOICES)
    year_of_graduation = forms.IntegerField(
        required=True, min_value=1900, max_value=3000,
        label="What year did you graduate?")
    race = forms.ChoiceField(required=True, choices=RACE_CHOICES)
    hispanic_latino = forms.ChoiceField(required=True,
                                        choices=HISPANIC_LATINO_CHOICES)
    age = forms.ChoiceField(required=True, choices=AGE_CHOICES)
    specialty = forms.ChoiceField(required=True, choices=SPECIALTY_CHOICES)

    def clean_is_faculty(self):
        data = self.cleaned_data['is_faculty']
        if data == '-----':
            raise forms.ValidationError(
                "Please indicate whether you are faculty or a student.")
        return data

    def clean_institute(self):
        data = self.cleaned_data['institute']
        if data == '-----':
            raise forms.ValidationError(
                "Please indicate what institution you are affiliated with.")
        return data

    def clean_gender(self):
        data = self.cleaned_data['gender']
        if data == '-----':
            raise forms.ValidationError("Please indicate your gender.")
        return data

    def clean_year_of_graduation(self):
        data = self.cleaned_data['year_of_graduation']
        if data == '-----':
            raise forms.ValidationError(
                "Please enter your year of graduation.")
        return data

    def clean_race(self):
        data = self.cleaned_data['race']
        if data == '-----':
            raise forms.ValidationError("Please indicate your race.")
        return data

    def clean_hispanic_latino(self):
        data = self.cleaned_data['hispanic_latino']
        if data == '-----':
            raise forms.ValidationError(
                "Please indicate if you are hispanic or latino.")
        return data

    def clean_age(self):
        data = self.cleaned_data['age']
        if data == '-----':
            raise forms.ValidationError("Please select an age.")
        return data

    def clean_specialty(self):
        data = self.cleaned_data['specialty']
        if data == '-----':
            raise forms.ValidationError("Please select a specialty.")
        return data

    def clean(self):
        cleaned_data = super(CreateAccountForm, self).clean()
        participant = cleaned_data.get("consent_participant")
        not_participant = cleaned_data.get("consent_not_participant")
        if participant and not_participant:
            # User should only select one field
            raise forms.ValidationError("You can be a participant or not, "
                                        "please select one or the other.")
        if not participant and not not_participant:
            # User should select at least one field
            raise forms.ValidationError("You must consent that you have read"
                                        " the document, whether you "
                                        "participate or not.")
        return cleaned_data


def user_created(sender, user, request, **kwargs):
    form = CreateAccountForm(request.POST)
    try:
        profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        profile = UserProfile(user=user)
    profile.institute = form.data['institute']
    profile.consent_participant = request.POST.get('consent_participant',
                                                   False)
    profile.consent_not_participant = \
        request.POST.get('consent_not_participant', False)
    profile.is_faculty = form.data['is_faculty']
    profile.year_of_graduation = form.data['year_of_graduation']
    profile.specialty = form.data['specialty']
    profile.gender = form.data['gender']
    profile.hispanic_latino = form.data['hispanic_latino']
    profile.race = form.data['race']
    profile.age = form.data['age']
    profile.save()


user_registered.connect(user_created)
