# Programmer: Chris Bunch (chris@appscale.com)


# General purpose library imports
import jinja2
import os
import sys
import urllib
import uuid
import webapp2


# Google App Engine API imports
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
      if len(upload_files) > 0:
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
        app.put()
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
], debug=True)
