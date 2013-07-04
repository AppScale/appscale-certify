# Programmer: Chris Bunch (chris@appscale.com)


# General purpose library imports
import cStringIO
import jinja2
import os
import urllib
import uuid
import webapp2
import zipfile


# Google App Engine API imports
from google.appengine.api import mail
from google.appengine.api import taskqueue
from google.appengine.api import users


# Google App Engine Datastore-related imports
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError


# Google App Engine Blobstore URL Handlers
from google.appengine.ext.webapp import blobstore_handlers, template


# Set up Jinja to read template files for our app
jinja_environment = jinja2.Environment(
  loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


class CertifiedApp(ndb.Model):
  name = ndb.StringProperty()
  size = ndb.IntegerProperty()
  owned_by = ndb.UserProperty()
  blob = ndb.BlobKeyProperty()
  is_examined = ndb.BooleanProperty()
  passed_certification = ndb.BooleanProperty()
  certification_info = ndb.TextProperty()
  analysis_report = ndb.TextProperty()


class BadLanguageException(Exception):
  """ BadLanguageException represents a custom exception class that is thrown
  when the AnalyzeApps class reads in zip files users upload that aren't
  Python or Java App Engine apps.
  """
  pass


class MainPage(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template = jinja_environment.get_template('templates/index.html')
    self.response.out.write(template.render(template_values))


class CertifyApps(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template_values['upload_url'] = blobstore.create_upload_url('/upload')
    template = jinja_environment.get_template('templates/certify.html')
    self.response.out.write(template.render(template_values))

  
class UploadApps(blobstore_handlers.BlobstoreUploadHandler):


  def post(self):
    try:
      upload_files = self.get_uploads('file')
      if len(upload_files) < 1:
        self.redirect('/')
        return

      blob_info = upload_files[0]
      appid = str(uuid.uuid4())
      app = CertifiedApp(id = appid)
      app.name = blob_info.filename
      app.size = blob_info.size
      app.owned_by = users.get_current_user()
      app.blob = blob_info.key()
      app.is_examined = False
      app.passed_certification = False
      app.certification_info = ""
      app.analysis_report = ""
      app.put()

      taskqueue.add(url='/analyze/{0}'.format(appid), method='POST')
      self.redirect('/view/' + appid)
    except CapabilityDisabledError:
      self.response.out.write('Uploading disabled')


class DownloadApps(blobstore_handlers.BlobstoreDownloadHandler):


  def get(self, resource):
    resource = str(urllib.unquote(resource))
    blob_info = blobstore.BlobInfo.get(resource)
    self.send_blob(blob_info)


class ViewApps(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    query = CertifiedApp.query(CertifiedApp.owned_by==users.get_current_user())
    template_values['all_my_apps'] = query.fetch()
    template = jinja_environment.get_template('templates/view_all.html')
    self.response.out.write(template.render(template_values))


class ViewAppCertification(webapp2.RequestHandler):


  def get(self, appid):
    template_values = get_common_template_params()
    template_values['app'] = CertifiedApp.get_by_id(appid)
    template = jinja_environment.get_template('templates/view.html')
    self.response.out.write(template.render(template_values))


  def post(self, appid):
    approval = self.request.get('approve')
    app = CertifiedApp.get_by_id(appid)
    app.is_examined = True
    if self.request.get('approve') == 'true':
      app.passed_certification = True
    else:
      app.passed_certification = False

    if self.request.get('certification_info'):
      app.certification_info = self.request.get('certification_info')
    app.put()
    self.redirect('/view/' + appid)


class WorkQueue(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template_values['apps_waiting'] = CertifiedApp.query(
      CertifiedApp.is_examined == False).fetch()
    template = jinja_environment.get_template('templates/workqueue.html')
    self.response.out.write(template.render(template_values))


class StatsPage(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template_values['apps_uploaded'] = CertifiedApp.query().count()
    template_values['apps_passed'] = CertifiedApp.query(
      CertifiedApp.is_examined == True,
      CertifiedApp.passed_certification == True).count()
    template_values['apps_failed'] = CertifiedApp.query(
      CertifiedApp.is_examined == True,
      CertifiedApp.passed_certification == False).count()
    template_values['apps_waiting'] = CertifiedApp.query(
      CertifiedApp.is_examined == False).count()
    template = jinja_environment.get_template('templates/stats.html')
    self.response.out.write(template.render(template_values))


class AnalyzeApps(webapp2.RequestHandler):


  NOT_A_ZIP_FILE_MESSAGE = """
The file you uploaded was not a zip file. Please upload a zip file for
certification and try again.
"""

  BAD_LANGUAGE_MESSAGE = """
We could not determine if your application was a Python or Java Google App
Engine application. If it is, please contact chris@appscale.com with the
file you uploaded.
"""


  def post(self, appid):
    # First, get the zip file from Blobstore.
    app = CertifiedApp.get_by_id(appid)
    blob_key = app.blob

    # Next, make sure it's actually a valid zip file.
    try:
      app_zip_file = zipfile.ZipFile(blobstore.BlobReader(blob_key))
    except zipfile.BadZipfile:
      reject_app(app, self.NOT_A_ZIP_FILE_MESSAGE)
      return

    # Next, find out if it's a Python app or a Java app.
    try:
      language = get_language_from_zip(app_zip_file)
    except BadLanguageException:
      reject_app(app, self.BAD_LANGUAGE_MESSAGE)
      return

    if language == "python":
      report = generate_python_report(app_zip_file)
      save_report(app, report)
      send_report(app)
      return
    else:
      reject_app(app, "java not implemented yet")
      return


def get_common_template_params():
  """Returns a dict of params that are commonly used by our templates, including
  information about the currently logged in user. """
  user = users.get_current_user()
  if user:
    is_logged_in = True
    is_admin = users.is_current_user_admin()
    user_name = user.nickname()
  else:
    is_logged_in = False
    is_admin = False
    user_name = ""

  return {
    "is_logged_in" : is_logged_in,
    "is_admin" : is_admin,
    "user_name" : user_name,
    "login_url" : users.create_login_url("/"),
    "logout_url" : users.create_logout_url("/")
  }


def reject_app(app, reason):
  """ Marks the given app as not being AppScale compatible, for the reason
  given by the caller.

  Args:
    app: The CertifiedApp model corresponding to the app to reject. Note that it
      must have been previously retrieved from the Datastore.
    reason: A str that indicates why this application is being rejected (e.g.,
      it wasn't a zip file, it wasn't an App Engine app).
  """
  app.is_examined = True
  app.passed_certification = False
  app.certification_info = reason
  app.put()
  send_report(app)


def get_language_from_zip(app_zip_file):
  """ Determines if the zip file given contains a Python or Java Google App
  Engine application.

  Args:
    app_zip_file: A ZipFile object, representing the zipped up Google App
      Engine application to examine.
  Returns:
    "python" if the app is a Python 2.5 or Python 2.7 Google App Engine app,
       or "java" if the app is a Java App Engine app.
  Raises:
    BadLanguageException: If the app isn't a Python or Java App Engine app.
  """
  # TODO(cgb): Support Go and PHP App Engine apps.
  for filename in app_zip_file.namelist():
    if filename.endswith("app.yaml"):
      return "python"
    elif filename.endswith("appengine-web.xml"):
      return "java"
  raise BadLanguageException


def generate_python_report(app_zip_file):
  """ Analyzes the ZipFile given to see what Google App Engine libraries this
  Python application uses.

  Args:
    app_zip_file: A ZipFile corresponding to the zipped up Google App Engine
      application to analyze.
  Returns:
    A str containing the App Engine imports this app uses, and the name of the
    file containing each import.
  """
  report = cStringIO.StringIO()

  for zipped_file in app_zip_file.infolist():
    # Only process files ending with .py.
    # TODO(cgb): Consider processing app.yaml as well.
    if not zipped_file.filename.endswith(".py"):
      continue

    with app_zip_file.open(zipped_file) as file_handle:
      for line in file_handle:
        if "google.appengine" in line:
          report.write("{0}: {1}".format(zipped_file.filename, line))

  report_as_str = report.getvalue().rstrip()
  report.close()
  return report_as_str


def save_report(app, report):
  """ Stores the given report in the Datastore, for app administrators to
  review at a later time.

  Args:
    app: The CertifiedApp model corresponding to the app to save a report for.
      Note that it must have been previously retrieved from the Datastore.
    report: A str that indicates what the analysis is for this application.
  """
  app.analysis_report = report
  app.put()


def send_report(app):
  """ E-mails the result of analyzing the uploaded application.

  Args:
    app: The CertifiedApp that we should e-mail information about.
  """
  sender_address = "Certification App <chris@appscale.com>"
  if app.is_examined:
    subject = "New App Automatically Certified!"
  else:
    subject = "New App Awaiting Certification!"

  if app.analysis_report:
    report = app.analysis_report
  else:
    report = "No information was gathered."

  body = """
{0} uploaded a new application, {1}, for certification. Check it out at:

http://certify.appscale.com/view/{2}

Analysis Report:
{3}
""".format(app.owned_by.nickname(), app.name, app.key.id(), report)
  mail.send_mail(sender_address, "chris@appscale.com", subject, body)


# Start up our app
app = webapp2.WSGIApplication([
  ('/', MainPage),
  ('/certify', CertifyApps),
  ('/upload', UploadApps),
  ('/download', DownloadApps),
  ('/view/all', ViewApps),
  ('/view/(.+)', ViewAppCertification),
  ('/workqueue', WorkQueue),
  ('/stats', StatsPage),
  ('/analyze/(.+)', AnalyzeApps),
], debug=True)
