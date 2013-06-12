# Programmer: Chris Bunch (chris@appscale.com)


# General purpose library imports
import jinja2
import os
import re
import urllib
import webapp2


# Google App Engine API imports
from google.appengine.api import users


# Google App Engine Datastore-related imports
from google.appengine.ext import ndb


# Set up Jinja to read template files for our app
jinja_environment = jinja2.Environment(
  loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


class MainPage(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template = jinja_environment.get_template('templates/index.html')
    self.response.out.write(template.render(template_values))


class CertifyApps(webapp2.RequestHandler):


  def get(self):
    template_values = get_common_template_params()
    template = jinja_environment.get_template('templates/certify.html')
    self.response.out.write(template.render(template_values))

  
  def post(self):
    pass


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
], debug=True)
