
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from groups.models import Group
from cources.models import Cource
from tasks.models import Task
from years.common import get_current_year, get_or_create_current_year
from years.models import Year

from xml.dom.minidom import parse
from optparse import make_option
import copy
import sys
import random
import string

def get_users_from_cs_xml(cs_xml_fn):
    doc = parse(cs_xml_fn)
    for student_el in doc.getElementsByTagName("student"):
        student = {
            'login'    : student_el.getAttribute('login'),
            'name'     : student_el.getAttribute('name'),
            'grp'      : student_el.getAttribute('grp'),
        }
        yield student

class Command(BaseCommand):
    help = "Copy cource"

    option_list = BaseCommand.option_list + (
        make_option('--cource_id',
            action='store',
            dest='cource_id',
            default=None,
            help='Cource id'),
        )

    @transaction.commit_on_success
    def handle(self, **options):
        cource_id = options['cource_id']
        if cource_id:
            cource_id = int(cource_id)

        if not cource_id:
            raise Exception("--cource_id is required!")

        cource_src = Cource.objects.get(id=cource_id)
        cource_dst = Cource()

        cource_dst.__dict__ = copy.deepcopy(cource_src.__dict__)
        cource_dst.id = None
        cource_dst.name += " copy"
        cource_dst.save()

        for task_src in Task.objects.filter(cource=cource_src):
            if task_src.has_parent():
                continue

            print "Copy task {0}".format(task_src.title.encode("utf-8"))
            task_dst = Task()
            task_dst.__dict__ = copy.deepcopy(task_src.__dict__)
            task_dst.id = None
            task_dst.cource = cource_dst
            task_dst.save()

            for subtask_src in task_src.get_subtasks():
                print ">Copy subtask {0}".format(subtask_src.title.encode("utf-8"))
                subtask_dst = Task()

                subtask_dst.__dict__ = copy.deepcopy(subtask_src.__dict__)
                subtask_dst.id = None
                subtask_dst.parent_task = task_dst
                subtask_dst.cource = cource_dst
                subtask_dst.save()
