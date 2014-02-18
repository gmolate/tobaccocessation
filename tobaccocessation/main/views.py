from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, render
from django.template import RequestContext
from django.utils import simplejson
from django.utils.encoding import smart_str
from pagetree.helpers import get_section_from_path, get_module, get_hierarchy
from pagetree.models import Section, UserLocation, UserPageVisit, Hierarchy
from quizblock.models import Submission, Response
from tobaccocessation.activity_prescription_writing.models import \
    ActivityState as PrescriptionWritingState, PrescriptionColumn
from tobaccocessation.activity_virtual_patient.models import \
    ActivityState as VirtualPatientActivityState, VirtualPatientColumn
from tobaccocessation.main.choices import RACE_CHOICES, SPECIALTY_CHOICES, \
    INSTITUTION_CHOICES, HISPANIC_LATINO_CHOICES, GENDER_CHOICES, choices_key
from tobaccocessation.main.models import QuickFixProfileForm, UserProfile
import csv


UNLOCKED = ['resources', 'faculty']  # special cases


class rendered_with(object):
    def __init__(self, template_name):
        self.template_name = template_name

    def __call__(self, func):
        def rendered_func(request, *args, **kwargs):
            items = func(request, *args, **kwargs)
            if isinstance(items, type({})):
                ctx = RequestContext(request)
                return render_to_response(self.template_name,
                                          items,
                                          context_instance=ctx)
            else:
                return items

        return rendered_func


@login_required
@rendered_with('main/index.html')
def index(request):
    """Need to determine here whether to redirect
    to profile creation or registraion and profile creation"""
    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        profile = None

    if profile is not None and profile.has_consented():
        profile = UserProfile.objects.get(user=request.user)
        hierarchy = get_hierarchy(name=profile.role())
        return {'user': request.user,
                'profile': profile,
                'hierarchy': hierarchy,
                'root': hierarchy.get_root()}
    else:
        return HttpResponseRedirect(reverse('create_profile'))


@user_passes_test(lambda u: u.is_staff)
@rendered_with('main/edit_page.html')
def edit_page(request, hierarchy, path):
    section = get_section_from_path(path, hierarchy)
    return dict(section=section,
                hierarchy=section.hierarchy,
                module=get_module(section),
                root=section.hierarchy.get_root())


@login_required
@rendered_with('main/page.html')
def page(request, hierarchy, path):
    section = get_section_from_path(path, hierarchy)
    h = section.hierarchy
    if request.method == "POST":
        # user has submitted a form. deal with it
        proceed = True
        for p in section.pageblock_set.all():
            if request.POST.get('action', '') == 'reset':
                section.reset(request.user)
                return HttpResponseRedirect(section.get_absolute_url())

            if hasattr(p.block(), 'needs_submit') and p.block().needs_submit():
                proceed = section.submit(request.POST, request.user)

        if request.is_ajax():
            json = simplejson.dumps({'submitted': 'True'})
            return HttpResponse(json, 'application/json')
        elif proceed:
            return HttpResponseRedirect(section.get_next().get_absolute_url())
        else:
            # giving them feedback before they proceed
            return HttpResponseRedirect(section.get_absolute_url())
    else:
        first_leaf = h.get_first_leaf(section)
        ancestors = first_leaf.get_ancestors()
        profile = UserProfile.objects.filter(user=request.user)[0]

        # Skip to the first leaf, make sure to mark these sections as visited
        if (section != first_leaf):
            profile.set_has_visited(ancestors)
            return HttpResponseRedirect(first_leaf.get_absolute_url())

        # the previous node is the last leaf, if one exists.
        prev_page = _get_previous_leaf(first_leaf)
        next_page = _get_next(first_leaf)

        # Is this section unlocked now?
        can_access = _unlocked(first_leaf, request.user, prev_page, profile)
        if can_access:
            profile.set_has_visited([section])

        module = None
        if not first_leaf.is_root() and len(ancestors) > 1:
            module = ancestors[1]

        allow_redo = False
        needs_submit = first_leaf.needs_submit()
        if needs_submit:
            allow_redo = first_leaf.allow_redo()

        return dict(request=request,
                    ancestors=ancestors,
                    profile=profile,
                    hierarchy=h,
                    section=first_leaf,
                    can_access=can_access,
                    module=module,
                    root=ancestors[0],
                    previous=prev_page,
                    next=next_page,
                    needs_submit=needs_submit,
                    allow_redo=allow_redo,
                    is_submitted=first_leaf.submitted(request.user))


def create_profile(request):
    """We actually dont need two views - can just return
    a registration form for non Columbia ppl and a
    QuickFixProfileForm for the Columbia ppl"""

    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile(user=request.user)

    form = QuickFixProfileForm()
    if request.method == 'POST':
        form = QuickFixProfileForm(request.POST)
        if form.is_valid():
            user_profile.institute = form.data['institute']
            user_profile.consent = True
            user_profile.is_faculty = form.data['is_faculty']
            user_profile.year_of_graduation = form.data['year_of_graduation']
            user_profile.specialty = form.data['specialty']
            user_profile.gender = form.data['gender']
            user_profile.hispanic_latino = form.data['hispanic_latino']
            user_profile.race = form.data['race']
            user_profile.age = form.data['age']
            user_profile.save()
            return HttpResponseRedirect('/')
    else:
        form = QuickFixProfileForm()

    return render(request, 'main/create_profile.html', {
        'form': form
    })


def accessible(section, user):
    try:
        previous = section.get_previous()
        return _unlocked(section, user, previous, user.get_profile())
    except AttributeError:
        return False


@login_required
def is_accessible(request, section_slug):
    section = Section.objects.get(slug=section_slug)
    previous = section.get_previous()
    response = {}

    if _unlocked(section, request.user, previous, request.user.get_profile()):
        response[section_slug] = "True"

    json = simplejson.dumps(response)
    return HttpResponse(json, 'application/json')


@login_required
def clear_state(request):
    try:
        request.user.get_profile().delete()
    except UserProfile.DoesNotExist:
        pass

    # clear visits & saved locations
    UserLocation.objects.filter(user=request.user).delete()
    UserPageVisit.objects.filter(user=request.user).delete()

    # clear quiz
    import quizblock
    quizblock.models.Submission.objects.filter(user=request.user).delete()

    # clear prescription writing
    PrescriptionWritingState.objects.filter(user=request.user).delete()

    # clear virtual patient
    VirtualPatientActivityState.objects.filter(user=request.user).delete()

    return HttpResponseRedirect(reverse("index"))


#####################################################################
## View Utility Methods

def _get_next(section):
    # next node in the depth-first traversal
    depth_first_traversal = Section.get_annotated_list(section.get_root())
    for (i, (s, ai)) in enumerate(depth_first_traversal):
        if s.id == section.id:
            if i < len(depth_first_traversal) - 1:
                return depth_first_traversal[i + 1][0]
            else:
                return None
    # made it through without finding ourselves? weird.
    return None


def _get_previous_leaf(section):
    depth_first_traversal = Section.get_annotated_list(section.get_root())
    for (i, (s, ai)) in enumerate(depth_first_traversal):
        if s.id == section.id:
            # first element is the root, so we don't want to return that
            prev = None
            while i > 1 and not prev:
                (node, x) = depth_first_traversal[i - 1]
                if node and len(node.get_children()) > 0:
                    i -= 1
                else:
                    prev = node
            return prev
    # made it through without finding ourselves? weird.
    return None


def _unlocked(section, user, previous, profile):
    if (section.hierarchy.name == 'faculty' and (
            not profile.is_role_faculty() and not user.is_staff)):
        return False

    # if the user can proceed past this section
    if (not section or
        section.is_root() or
        profile.get_has_visited(section) or
        section.slug in UNLOCKED or
            section.hierarchy.name in UNLOCKED):
        return True

    if not previous or previous.is_root():
        return True

    for pbl in previous.pageblock_set.all():
        if hasattr(pbl.block(), 'unlocked'):
            if not pbl.block().unlocked(user):
                return False

    if previous.slug in UNLOCKED:
        return True

    return profile.get_has_visited(previous)


#####################################################################
## Reporting

def clean_header(s):
    s = s.replace('<p>', '')
    s = s.replace('</p>', '')
    s = s.replace('</div>', '')
    s = s.replace('\n', '')
    s = s.replace('\r', '')
    s = s.replace('<', '')
    s = s.replace('>', '')
    s = s.replace('\'', '')
    s = s.replace('\"', '')
    s = s.replace(',', '')
    s = s.encode('utf-8')
    return s


class QuestionColumn(object):
    def __init__(self, hierarchy, question, answer=None):
        self.hierarchy = hierarchy
        self.question = question
        self.answer = answer

        self._submission_cache = Submission.objects.filter(
            quiz=self.question.quiz)
        self._response_cache = Response.objects.filter(
            question=self.question)
        self._answer_cache = self.question.answer_set.all()

    def question_id(self):
        return "%s_%s" % (self.hierarchy.id, self.question.id)

    def question_answer_id(self):
        return "%s_%s_%s" % (self.hierarchy.id,
                             self.question.id,
                             self.answer.id)

    def identifier(self):
        if self.question and self.answer:
            return self.question_answer_id()
        else:
            return self.question_id()

    def key_row(self):
        row = [self.question_id(),
               self.hierarchy.name,
               self.question.question_type,
               clean_header(self.question.text)]
        if self.answer:
            row.append(self.answer.id)
            row.append(clean_header(self.answer.label))
        return row

    def user_value(self, user):
        r = self._submission_cache.filter(user=user).order_by("-submitted")
        if r.count() == 0:
            # user has not submitted this form
            return ""
        submission = r[0]
        r = self._response_cache.filter(submission=submission)
        if r.count() > 0:
            if (self.question.is_short_text() or
                    self.question.is_long_text()):
                return r[0].value
            elif self.question.is_multiple_choice():
                if self.answer.value in [res.value for res in r]:
                    return self.answer.id
            else:  # single choice
                for a in self._answer_cache:
                    if a.value == r[0].value:
                        return a.id

        return ''

    @classmethod
    def all(cls, hierarchy, section, key_only=True):
        columns = []
        content_type = ContentType.objects.get(name='quiz',
                                               app_label='quizblock')

        # quizzes
        for p in section.pageblock_set.filter(content_type=content_type):
            for q in p.block().question_set.all():
                if q.answerable() and (key_only or q.is_multiple_choice()):
                    # need to make a column for each answer
                    for a in q.answer_set.all():
                        columns.append(
                            QuestionColumn(hierarchy=hierarchy,
                                           question=q, answer=a))
                else:
                    columns.append(QuestionColumn(hierarchy=hierarchy,
                                                  question=q))

        return columns


def _get_columns(key_only):
    columns = []
    exclusions = ['faculty', 'resources']
    for hierarchy in Hierarchy.objects.all().exclude(name__in=exclusions):
        for section in hierarchy.get_root().get_descendants():
            columns += QuestionColumn.all(hierarchy, section, key_only) + \
                PrescriptionColumn.all(hierarchy, section, key_only) + \
                VirtualPatientColumn.all(hierarchy, section, key_only)
    return columns


@user_passes_test(lambda u: u.is_superuser)
def all_results_key(request):
    """
        A "key" for all questions and answers in the system.
        * One row for short/long text questions
        * Multiple rows for single/multiple-choice questions.
        Each question/answer pair get a row
        itemIdentifier - unique system identifier,
            concatenates hierarchy id, item type string,
            page block id (if necessary) and item id
        hierarchy - first child label in the hierarchy
        itemType - [question, discussion topic, referral field]
        itemText - identifying text for the item
        answerIdentifier - for single/multiple-choice questions. an answer id
        answerText
    """
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = \
        'attachment; filename=tobacco_response_key.csv'
    writer = csv.writer(response)
    headers = ['itemIdentifier', 'hierarchy', 'itemType', 'itemText',
               'answerIdentifier', 'answerText']
    writer.writerow(headers)

    # key to profile choices / values
    # username, e-mail, gender, is_faculty, institution, specialty
    #    hispanic/latino, race, year_of_graduation, consent, % complete
    writer.writerow(['username', 'profile', 'string', 'Username'])
    writer.writerow(['user e-mail', 'profile', 'string', 'User E-mail'])
    choices_key(writer, GENDER_CHOICES, 'gender', 'single_choice')
    writer.writerow(['faculty', 'profile', 'boolean', 'Is Faculty'])
    choices_key(writer, INSTITUTION_CHOICES, 'institution', 'single_choice')
    choices_key(writer, SPECIALTY_CHOICES, 'specialty', 'single_choice')
    choices_key(writer, HISPANIC_LATINO_CHOICES,
                'hispanic_latino', 'single_choice')
    choices_key(writer, RACE_CHOICES, 'race', 'single_choice')
    writer.writerow(['graduation year',
                     'profile', 'number', 'Graduation Year'])
    writer.writerow(['consent', 'profile', 'boolean', 'Has Consented'])
    writer.writerow(['complete', 'profile', 'percent', 'Percent Complete'])

    # quizzes, prescription writing, virtual patient keys -- data / values
    for column in _get_columns(True):
        writer.writerow(column.key_row())

    return response


@user_passes_test(lambda user: user.is_superuser)
@rendered_with("main/all_results.html")
def all_results(request):
    """
    All system results
    * One or more column for each question in system.
        ** 1 column for short/long text. label = itemIdentifier from key
        ** 1 column for single choice. label = itemIdentifier from key
        ** n columns for multiple choice: 1 column for each possible answer
           *** column labeled as itemIdentifer_answer.id

        * One row for each user in the system.
            1. username
            2 - n: answers
                * short/long text. text value
                * single choice. answer.id
                * multiple choice.
                    ** answer id is listed in each question/answer
                    column the user selected
                * Unanswered fields represented as an empty cell
    """
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = \
        'attachment; filename=tobacco_responses.csv'
    writer = csv.writer(response)

    columns = _get_columns(False)

    headers = ['username', 'email', 'gender', 'is faculty', 'institute',
               'specialty', 'hispanic_latino', 'race', 'year_of_graduation',
               'consent', 'percent_complete']
    for column in columns:
        headers += [column.identifier()]
    writer.writerow(headers)

    # Only look at users who have create a profile + consented
    profiles = UserProfile.objects.filter(consent=True)
    for profile in profiles:
        row = [profile.user.username, profile.user.email, profile.gender,
               profile.is_role_faculty(), profile.institute,
               profile.specialty, profile.hispanic_latino, profile.race,
               profile.year_of_graduation, profile.has_consented(),
               profile.percent_complete()]

        for column in columns:
            v = smart_str(column.user_value(profile.user))
            row.append(v)

        writer.writerow(row)

    return response
