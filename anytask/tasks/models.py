# coding: utf-8

from django.db import models
from datetime import datetime
from django.utils.translation import ugettext as _
from django.db.models.signals import post_save, pre_delete

from cources.models import Cource
from groups.models import Group

from django.db.models import Q

from django.contrib.auth.models import User

from datetime import timedelta
import copy

class Task(models.Model):
    title = models.CharField(max_length=254, db_index=True, null=True, blank=True)
    cource = models.ForeignKey(Cource, db_index=True, null=False, blank=False)
    group = models.ForeignKey(Group, db_index=False, null=True, blank=True, default=None)
    weight = models.IntegerField(db_index=True, null=False, blank=False, default=0)

    is_hidden = models.BooleanField(db_index=True, null=False, blank=False, default=False)

    parent_task = models.ForeignKey('self', db_index=True, null=True, blank=True, related_name='parent_task_set')

    task_text = models.TextField(null=True, blank=True, default=None)

    score_max = models.IntegerField(db_index=True, null=False, blank=False, default=0)

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    updated_by = models.ForeignKey(User, db_index=False, null=True, blank=True)

    def __unicode__(self):
        return unicode(self.title)

    def user_can_take_task(self, user):
        cource = self.cource

        if user.is_anonymous():
            return (False, '')

        if self.is_hidden:
            return (False, '')

        if cource.take_policy != Cource.TAKE_POLICY_SELF_TAKEN:
            return (False, u'')

        if not self.cource.groups.filter(students=user).count() and not self.cource.students.filter(id=user.id).count():
            return (False, u'')

        if cource.max_users_per_task:
            if TaskTaken.objects.filter(task=self).filter(Q( Q(status=TaskTaken.STATUS_TAKEN) | Q(status=TaskTaken.STATUS_SCORED))).count() >= cource.max_users_per_task:
                return (False, u'Задача не может быть взята более чем {0} студентами'.format(cource.max_users_per_task))

        if cource.max_tasks_without_score_per_student:
            if TaskTaken.objects.filter(user=user).filter(status=TaskTaken.STATUS_TAKEN).count() >= cource.max_tasks_without_score_per_student:
                return (False, u'')

        if Task.objects.filter(parent_task=self).count() > 0:
            return (False, u'')

        if TaskTaken.objects.filter(task=self).filter(user=user).filter(Q( Q(status=TaskTaken.STATUS_TAKEN) | Q(status=TaskTaken.STATUS_SCORED))).count() != 0:
            return (False, u'')

        if self.parent_task is not None:
            tasks = Task.objects.filter(parent_task=self.parent_task)
            if TaskTaken.objects.filter(user=user).filter(task__in=tasks).exclude(status=TaskTaken.STATUS_CANCELLED).count() > 0:
                return (False, u'')

        try:
            task_taken = TaskTaken.objects.filter(task=self).filter(user=user).get(status=TaskTaken.STATUS_BLACKLISTED)
            black_list_expired_date = task_taken.update_time + timedelta(days=cource.days_drop_from_blacklist)
            return (False, u'Вы сможете взять эту задачу с {0}'.format(black_list_expired_date.strftime("%d.%m.%Y")))
        except TaskTaken.DoesNotExist:
            pass

        if TaskTaken.objects.filter(task=self).filter(user=user).filter(status=TaskTaken.STATUS_SCORED).count() != 0:
            return (False, u'')

        return (True, u'')

    def user_can_cancel_task(self, user):
        if user.is_anonymous() or self.cource.take_policy != Cource.TAKE_POLICY_SELF_TAKEN or self.is_hidden:
            return False
        if TaskTaken.objects.filter(task=self).filter(user=user).filter(status=TaskTaken.STATUS_TAKEN).count() != 0:
            return True
        return False

    def user_can_score_task(self, user):
        if user.is_anonymous():
            return False

        return self.cource.user_is_teacher(user)

    def user_can_pass_task(self, user):
        if user.is_anonymous():
            return False

        if not self.cource.rb_integrated:
            return False

        if self.cource.take_policy == Cource.TAKE_POLICY_ALL_TASKS_TO_ALL_STUDENTS and \
           self.user_can_take_task(user):

            return True

        try:
            task_taken = self.get_task_takens().get(user=user)
            return (task_taken.status == TaskTaken.STATUS_TAKEN or task_taken.status == TaskTaken.STATUS_SCORED)
        except TaskTaken.DoesNotExist:
            return False
        return False

    def has_parent(self):
        return self.parent_task is not None

    def has_subtasks(self):
        return Task.objects.filter(parent_task=self).count() > 0

    def get_subtasks(self):
        return Task.objects.filter(parent_task=self)

    def get_task_takens(self):
        return TaskTaken.objects.filter(task=self).filter(Q( Q(status=TaskTaken.STATUS_TAKEN) | Q(status=TaskTaken.STATUS_SCORED)))

    def add_user_properties(self, user):
        self.can_take = self.user_can_take_task(user)
        self.can_cancel = self.user_can_cancel_task(user)
        self.can_score = self.user_can_score_task(user)
        self.can_pass = self.user_can_pass_task(user)
        self.is_shown = not self.is_hidden or self.cource.user_is_teacher(user)

class TaskLog(models.Model):
    title = models.CharField(max_length=254, db_index=True, null=True, blank=True)
    cource = models.ForeignKey(Cource, db_index=False, null=False, blank=False)
    group = models.ForeignKey(Group, db_index=False, null=True, blank=True, default=None)
    weight = models.IntegerField(db_index=False, null=False, blank=False, default=0)

    parent_task = models.ForeignKey('self', db_index=True, null=True, blank=True, related_name='parent_task_set')

    task_text = models.TextField(null=True, blank=True, default=None)

    score_max = models.IntegerField(db_index=False, null=False, blank=False, default=0)

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    updated_by = models.ForeignKey(User, db_index=False, null=True, blank=True)

    def __unicode__(self):
        return unicode(self.title)

class TaskTaken(models.Model):

    STATUS_TAKEN = 0
    STATUS_CANCELLED = 1
    STATUS_BLACKLISTED = 2
    STATUS_SCORED = 3
    STATUS_DELETED = 4

    user = models.ForeignKey(User, db_index=True, null=False, blank=False)
    task = models.ForeignKey(Task, db_index=True, null=False, blank=False)

    TASK_TAKEN_STATUSES = (
        (STATUS_TAKEN,          _(u'Task taken')),
        (STATUS_CANCELLED,      _(u'Task cancelled')),
        (STATUS_BLACKLISTED,    _(u'Task blacklisted')),
        (STATUS_SCORED,         _(u'Task scored')),
        (STATUS_DELETED,        _(u'TaskTaken deleted'))
    )
    status = models.IntegerField(max_length=1, choices=TASK_TAKEN_STATUSES, db_index=True, null=False, blank=False, default=0)

    score = models.IntegerField(db_index=False, null=False, blank=False, default=0)
    scored_by = models.ForeignKey(User, db_index=True, null=True, blank=True, related_name='task_taken_scored_by_set')

    teacher_comments = models.TextField(db_index=False, null=True, blank=True, default='')

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    class Meta:
        unique_together = (("user", "task"),)

    def __unicode__(self):
        return unicode(self.task) + " (" + unicode(self.user) + ")"

class TaskTakenLog(models.Model):
    user = models.ForeignKey(User, db_index=False, null=False, blank=False)
    task = models.ForeignKey(Task, db_index=False, null=False, blank=False)

    status = models.IntegerField(max_length=1, choices=TaskTaken.TASK_TAKEN_STATUSES, db_index=True, null=False, blank=False, default=0)

    score = models.IntegerField(db_index=False, null=False, blank=False, default=0)
    scored_by = models.ForeignKey(User, db_index=False, null=True, blank=True, related_name='task_taken_log_scored_by_set')

    teacher_comments = models.TextField(db_index=False, null=True, blank=True, default='')

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    def __unicode__(self):
        return unicode(self.task) + " (" + unicode(self.user) + ")"


def task_save_to_log_post_save(sender, instance, created, **kwargs):
    task_log = TaskLog()
    task_log_dict  = copy.deepcopy(instance.__dict__)
    task_log_dict['id'] = None
    task_log.__dict__ = task_log_dict
    task_log.save()

def task_taken_save_to_log_post_save(sender, instance, created, **kwargs):
    task_taken_log = TaskTakenLog()
    task_taken_log_dict  = copy.deepcopy(instance.__dict__)
    task_taken_log_dict['id'] = None
    task_taken_log.__dict__ = task_taken_log_dict
    task_taken_log.save()

def task_taken_save_to_log_pre_delete(sender, instance, **kwargs):
    task_taken_log = TaskTakenLog()
    task_taken_log_dict  = copy.deepcopy(instance.__dict__)
    task_taken_log_dict['id'] = None
    task_taken_log.__dict__ = task_taken_log_dict
    task_taken_log.scored_by = None
    task_taken_log.status = TaskTaken.STATUS_DELETED
    task_taken_log.save()

post_save.connect(task_save_to_log_post_save, sender=Task)
post_save.connect(task_taken_save_to_log_post_save, sender=TaskTaken)
pre_delete.connect(task_taken_save_to_log_pre_delete, sender=TaskTaken)
