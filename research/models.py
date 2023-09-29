from django.db import models
from datetime import datetime
import traceback
import os
from django.conf import settings

from datasets.models import Dataset
from models.models import ArtmModel
from assessment.models import AssessmentProblem
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from shutil import rmtree
from django.contrib import admin


class Research(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True)
    model = models.ForeignKey(ArtmModel, on_delete=models.CASCADE, null=True, blank=True)
    problem = models.ForeignKey(AssessmentProblem, on_delete=models.CASCADE, null=True, blank=True)
    researcher = models.ForeignKey(User, on_delete=models.CASCADE, null=False)
    script_name = models.TextField(null=False)
    start_time = models.DateTimeField(null=False, default=datetime.now)
    finish_time = models.DateTimeField(null=True, blank=True)
    sealed = models.BooleanField(default=False)
    # 1-running,2-OK,3-errror,4-interrupted, 5-backup
    status = models.IntegerField(null=False, default=0)
    error_message = models.TextField(null=True, blank=True)
    is_private = models.BooleanField(default=False)

    def run(self):
        with open(self.get_report_file(), "w", encoding="utf-8") as f:
            f.write("<html>\n<head><meta charset='utf-8'></head>\n<body>")
            f.write("<h1>Research report</h1>\n")
            f.write("<p>Research id: %d<br>\n" % self.id)
            f.write("Dataset: %s<br>\n" % str(self.dataset))
            if self.model:
                f.write("Model: %s (id=%d)<br>\n" %
                        (str(self.model), self.model.id))
            if self.problem:
                f.write("Assesment problem: %s<br>\n" % str(self.problem))
            f.write("Script: %s<br>\n" % self.script_name)
            f.write("Researcher: %s<br>\n" % self.researcher.username)
            f.write("Research started: %s</p>\n" %
                    self.start_time.strftime("%d.%m.%y %H:%M:%S"))
            f.write("<hr>\n")

        script_file_name = os.path.join(
            settings.BASE_DIR, "algo", "research", self.script_name)
        self.img_counter = 0

        try:
            with open(script_file_name, "r", encoding="utf-8") as f:
                code = compile(f.read(), script_file_name, "exec")
            exec(code, {"research": self})
        except BaseException:
            self.status = 3
            self.error_message = traceback.format_exc()
            self.finish_time = datetime.now()
            self.save()
            return

        self.finish_time = datetime.now()
        self.status = 2
        self.save()

        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write("<hr>\n")
            f.write("<p>Research finished: %s</p>\n" %
                    self.finish_time.strftime("%d.%m.%y %H:%M:%S"))
            f.write("</body>\n</html>\n")

    def report_html(self, text):
        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def report(self, text):
        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write(text + "<br>\n")

    def log(self, text):
        self.report("[LOG] %s" % text)

    def report_p(self, text=""):
        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write("<p>" + text + "</p>\n")

    def gca(self, figsize=None):
        self.figure = self.get_figure(figsize=figsize)
        return self.figure.gca()

    def get_figure(self, figsize=None):
        import matplotlib as mpl
        mpl.use("Agg")

        import matplotlib.pyplot as plt
        self.figure = plt.figure(figsize=figsize)
        return self.figure

    def show_matrix(self, m):
        self.gca().imshow(m, interpolation="nearest")
        self.report_picture()

    def report_picture(
            self,
            height=400,
            width=400,
            align='left',
            bbox_extra_artists=None,
            name=None):
        self.img_counter += 1
        file_name = str(self.img_counter) + '.png'
        eps_file_name = str(self.img_counter) + '.eps'
        if name:
            eps_file_name = name + ".eps"
        self.figure.savefig(
            os.path.join(
                self.get_pic_folder(),
                eps_file_name),
            bbox_extra_artists=bbox_extra_artists,
            bbox_inches='tight')
        self.figure.savefig(
            os.path.join(
                self.get_pic_folder(),
                file_name),
            bbox_extra_artists=bbox_extra_artists,
            bbox_inches='tight')
        self.figure.clf()
        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write(
                ("<div align='%s'><a href='pic/%s'>"
                 "<img src='pic/%s' width='%d' heigth='%d' />"
                 "</a></div>\n") %
                (align, eps_file_name, file_name, width, height))
        del self.figure

    def latex_table(self, table, format):
        nrows = len(table)
        ncols = len(table[0])

        ans = "\\begin{tabular}{|%s|}\n" % "|".join(
            ["c" for i in range(ncols)])
        for row in table:
            ans += "\\hline\n"
            for i in range(ncols):
                ans += (format % row[i])
                if i == ncols - 1:
                    ans += " \\\\\n"
                else:
                    ans += " & "

        ans += "\\hline\n"
        ans += "\\end{tabular}\n"
        return ans

    def report_table(self, table, format="%s"):
        with open(self.get_report_file(), "a", encoding="utf-8") as f:
            f.write('<table border="1" cellpadding="0" cellspacing="0">\n')
            for row in table:
                f.write("<tr>\n")
                for cell in row:
                    if format:
                        f.write("<td>")
                        f.write(format % cell)
                        f.write("</td>")
                f.write("</tr>\n")
            f.write("</table>\n")
            self.img_counter += 1
            f.write(
                "<p><a href='pic/%d.txt'>Table in LaTeX</a></p>" %
                self.img_counter)

        table_file = os.path.join(self.get_pic_folder(),
                                  str(self.img_counter) + '.txt')
        with open(table_file, "w", encoding='utf-8') as f:
            f.write(self.latex_table(table, format))

    def get_folder(self):
        path = os.path.join(settings.DATA_DIR, "research", str(self.id))
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_pic_folder(self):
        path = os.path.join(settings.DATA_DIR, "research", str(self.id), "pic")
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_report_file(self):
        return os.path.join(self.get_folder(), "report.html")

    def __str__(self):
        return "Research %d (%s, %s)" % (
            self.id, str(self.dataset), self.script_name)

    def duration(self):
        if self.finish_time:
            dt = self.finish_time - self.start_time
        else:
            dt = datetime.now() - self.start_time
        seconds = dt.seconds
        return "{:02}:{:02}".format(seconds // 60, seconds % 60)


def on_start():
    # print ("ENTRY POINT 2")
    for research in Research.objects.filter(status=1):
        research.status = 4
        research.save()


@receiver(pre_delete, sender=Research, dispatch_uid='research_delete_signal')
def remove_research_files(sender, instance, using, **kwargs):
    if instance.sealed:
        backup = Research()
        backup.researcher = instance.researcher
        backup.status = 5
        backup.sealed = True
        backup.start_time = instance.start_time
        backup.finish_time = instance.finish_time
        backup.script_name = instance.script_name
        backup.save()
        os.rename(
            instance.get_folder(), os.path.join(
                settings.DATA_DIR, "research", str(
                    backup.id)))
    else:
        try:
            rmtree(instance.get_folder())
        except BaseException:
            pass


admin.site.register(Research)
