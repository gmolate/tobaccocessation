from django.contrib.auth.models import User
from django.test import TestCase
from pagetree.models import Hierarchy, Section
from tobaccocessation.main.models import UserProfile
from tobaccocessation.activity_prescription_writing.models import Medication, \
    Block


class UserProfileTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('test_student',
                                             'test@ccnmtl.com',
                                             'testpassword')
        UserProfile.objects.get_or_create(user=self.user,
                                          gender='M',
                                          is_faculty='ST',
                                          institute='I1',
                                          specialty='S1',
                                          hispanic_latino='Y',
                                          year_of_graduation=2015,
                                          consent=True)

        self.hierarchy = Hierarchy(name="main", base_url="/")
        self.hierarchy.save()

        self.root = Section.add_root(label="Root", slug="",
                                     hierarchy=self.hierarchy)

        self.root.append_child("Section 1", "section-1")
        self.root.append_child("Section 2", "section-2")

        self.section1 = Section.objects.get(slug="section-1")
        self.section2 = Section.objects.get(slug="section-2")

    def tearDown(self):
        self.user.delete()
        self.hierarchy.delete()

    def test_set_has_visited(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        self.assertFalse(profile.get_has_visited(self.section1))
        self.assertFalse(profile.get_has_visited(self.section2))

        profile.set_has_visited([self.section1, self.section2])

        self.assertTrue(profile.get_has_visited(self.section1))
        self.assertTrue(profile.get_has_visited(self.section2))

    def test_last_location(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        # By default, the 1st leaf is returned if there are no visits
        self.assertEquals(profile.last_location(), self.section1)

        profile.set_has_visited([self.section1])
        self.assertEquals(profile.last_location(), self.section1)

        profile.set_has_visited([self.section2])
        self.assertEquals(profile.last_location(), self.section2)

        profile.set_has_visited([self.section1])
        self.assertEquals(profile.last_location(), self.section1)

    def test_user_unicode(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)
        uni_name = UserProfile.__unicode__(profile)
        self.assertEqual(uni_name, 'test_student')

    def test_user_display_name(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)
        display_name = UserProfile.display_name(profile)
        self.assertEqual(display_name, 'test_student')

    def test_percent_complete(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        self.assertEquals(0, profile.percent_complete())

        profile.set_has_visited([self.root, self.section1])
        self.assertEquals(66, profile.percent_complete())
        profile.set_has_visited([self.section2])
        self.assertEquals(100, profile.percent_complete())

    def test_percent_complete_null_hierarchy(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)
        profile.speciality = "pediatrics"

        self.assertEquals(0, profile.percent_complete())

    def test_is_student(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        profile.is_faculty = 'FA'
        profile.save()
        self.assertFalse(profile.is_student())

        profile.is_faculty = 'OT'
        profile.save()
        self.assertFalse(profile.is_student())

        profile.is_faculty = 'ST'
        profile.save()
        self.assertTrue(profile.is_student())

    def test_default_role(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        self.assertEquals("main", profile.role())

    def test_role(self):
        user = User.objects.get(username='test_student')
        profile = UserProfile.objects.get(user=user)

        profile.is_faculty = 'ST'
        profile.save()
        self.assertEquals(profile.role(), "main")

        profile.is_faculty = 'FA'
        profile.specialty = 'S1'
        profile.save()
        self.assertEquals(profile.role(), "general")

        profile.specialty = 'S2'  # Pre-Doctoral Student'
        profile.save()
        self.assertEquals(profile.role(), "main")

        profile.specialty = 'S3'  # Endodontics
        profile.save()
        self.assertEquals(profile.role(), "endodontics")

        profile.specialty = 'S4'  # Oral and Maxillofacial Surgery'
        profile.save()
        self.assertEquals(profile.role(), "surgery")

        profile.specialty = 'S5'  # Pediatric Dentistry
        profile.save()
        self.assertEquals(profile.role(), "pediatrics")

        profile.specialty = 'S6'  # Periodontics
        profile.save()
        self.assertEquals(profile.role(), "perio")

        profile.specialty = 'S7'  # Prosthodontics
        profile.save()
        self.assertEquals(profile.role(), "general")

        profile.specialty = 'S8'  # Orthodontics
        profile.save()
        self.assertEquals(profile.role(), "orthodontics")

        profile.specialty = 'S9'  # Other
        profile.save()
        self.assertEquals(profile.role(), "main")

        profile.specialty = 'S10'  # Dental Public Health
        profile.save()
        self.assertEquals(profile.role(), "main")


class TestModelsOther(TestCase):
    def setUp(self):
        self.block = Block()
        self.block.save()

    def test_block_submit_false(self):
        self.assertEquals(self.block.needs_submit(), False)

    def test_block_edit_form(self):
        self.form_test = self.block.edit_form()
        self.assertIsNotNone(self.form_test)

    def test_block_add_form(self):
        self.add_form_test = self.block.add_form()
        self.assertIsNotNone(self.add_form_test)


    # def test_block_create(self):
    #     c = Client()
    #     self.request = c.post('/some_page/', {
    #         'medication_name': 'medication name', 'show_correct': False})
    #     self.block_create = self.block.create(self.request)
    #     self.assertIsNotNone(self.block_create)


class TestModelsNoUser(TestCase):
    def setUp(self):
        self.medication = Medication(name="medication name", refills=2,
                                     sort_order=2, rx_count=1)
        self.medication.save()
        self.block = Block(medication_name="block medication")
        self.block.save()

    def test_medication(self):
        self.assertEquals("medication name", unicode(self.medication))

    def test_block_submit_false(self):
        self.assertEquals(self.block.needs_submit(), False)

    def test_block_edit_form(self):
        self.form_test = self.block.edit_form()
        self.assertIsNotNone(self.form_test)

    def test_block_add_form(self):
        self.add_form_test = self.block.add_form()
        self.assertIsNotNone(self.add_form_test)

    def test_block_medication_method(self):
        self.test_medication = self.block.medication()
        self.assertIsNotNone(self.test_medication)


class TestModelsMedBlock(TestCase):
    def setUp(self):
        self.medication = Medication(name="medication name", refills=2,
                                     sort_order=2, rx_count=1)
        self.medication.save()
        self.block = Block(medication_name="block medication")
        self.block.save()

    def test_medication(self):
        self.assertEquals("medication name", unicode(self.medication))

    def test_block_submit_false(self):
        self.assertEquals(self.block.needs_submit(), False)

    def test_block_edit_form(self):
        self.form_test = self.block.edit_form()
        self.assertIsNotNone(self.form_test)

    def test_block_add_form(self):
        self.add_form_test = self.block.add_form()
        self.assertIsNotNone(self.add_form_test)

    def test_block_medication_method(self):
        self.test_medication = self.block.medication()
        self.assertIsNotNone(self.test_medication)
