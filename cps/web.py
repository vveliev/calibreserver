#!/usr/bin/env python
# -*- coding: utf-8 -*-

import mimetypes
mimetypes.add_type('application/xhtml+xml','.xhtml')
from flask import Flask, render_template, session, request, redirect, url_for, send_from_directory, make_response, g, flash
from cps import db, config, ub, helper
import os
from sqlalchemy.sql.expression import func
from math import ceil
from flask.ext.login import LoginManager, login_user, logout_user, login_required, current_user
from flask.ext.principal import Principal, Identity, AnonymousIdentity, identity_changed
from flask.ext.babel import Babel
from flask.ext.babel import gettext as _
import requests, zipfile
from werkzeug.security import generate_password_hash, check_password_hash
from babel import Locale as LC
from cps.feed import feed

app = (Flask(__name__))
app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'

if config.DEVELOPMENT:
    from flask_debugtoolbar import DebugToolbarExtension
    app.debug = True
    toolbar = DebugToolbarExtension(app)

Principal(app)

lm = LoginManager(app)
lm.init_app(app)
lm.login_view = 'login'

babel = Babel(app)

app.register_blueprint(feed)

class MyAnonymousUser(object):
    def __init__(self):
        self.random_books = 1

    def is_active(self):
        return False

    def is_authenticated(self):
        return False

    def is_anonymous(self):
        return True

    def get_id(self):
        return unicode(self.id)

lm.anonymous_user = MyAnonymousUser

@babel.localeselector
def get_locale():
    # if a user is logged in, use the locale from the user settings
    user = getattr(g, 'user', None)
    if user is not None and hasattr(user, "locale"):
         return user.locale
    # otherwise try to guess the language from the user accept
    # header the browser transmits.  We support de/fr/en in this
    # example.  The best match wins.
    return request.accept_languages.best_match(['de', "en"])

@babel.timezoneselector
def get_timezone():
    user = getattr(g, 'user', None)
    if user is not None:
        return user.timezone

@lm.user_loader
def load_user(id):
    return ub.session.query(ub.User).filter(ub.User.id == int(id)).first()


@lm.header_loader
def load_user_from_header(header_val):
    print header_val
    if header_val.startswith('Basic '):
        header_val = header_val.replace('Basic ', '', 1)
        print header_val
    try:
        header_val = base64.b64decode(header_val)
        print header_val
    except TypeError:
        pass
    return ub.session.query(ub.User).filter(ub.User.password == header_val).first()

#simple pagination for the feed
class Pagination(object):

    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

##pagination links in jinja
def url_for_other_page(page):
    args = request.view_args.copy()
    args['page'] = page
    return url_for(request.endpoint, **args)

app.jinja_env.globals['url_for_other_page'] = url_for_other_page

@app.before_request
def before_request():
    g.user = current_user
    g.public_shelfes = ub.session.query(ub.Shelf).filter(ub.Shelf.is_public == 1).all()


@app.route("/", defaults={'page': 1})
@app.route('/page/<int:page>')
def index(page):

    if not helper.check_for_user():
        return redirect(url_for('setup'))

    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    if page == 1:
        entries = db.session.query(db.Books).order_by(db.Books.last_modified.desc()).limit(config.NEWEST_BOOKS)
    else:
        off = int(int(config.NEWEST_BOOKS) * (page - 1))
        entries = db.session.query(db.Books).order_by(db.Books.last_modified.desc()).offset(off).limit(config.NEWEST_BOOKS)
    pagination = Pagination(page, config.NEWEST_BOOKS, len(db.session.query(db.Books).all()))
    return render_template('index.html', random=random, entries=entries, pagination=pagination, title=_("Latest Books"))

@app.route("/hot", defaults={'page': 1})
@app.route('/hot/page/<int:page>')
def hot_books(page):
    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    off = int(int(6) * (page - 1))
    all_books = ub.session.query(ub.Downloads, ub.func.count(ub.Downloads.book_id)).order_by(ub.func.count(ub.Downloads.book_id).desc()).group_by(ub.Downloads.book_id)
    hot_books = all_books.offset(off).limit(config.NEWEST_BOOKS)
    entries = list()
    for book in hot_books:
        entries.append(db.session.query(db.Books).filter(db.Books.id == book.Downloads.book_id).first())

    pagination = Pagination(page, config.NEWEST_BOOKS, len(all_books.all()))
    return render_template('index.html', random=random, entries=entries, pagination=pagination, title=_("Hot Books"))

@app.route("/stats")
def stats():
    counter = len(db.session.query(db.Books).all())
    return render_template('stats.html', counter=counter, title=_("Statistics"))

@app.route("/discover", defaults={'page': 1})
@app.route('/discover/page/<int:page>')
def discover(page):
    if page == 1:
        entries = db.session.query(db.Books).order_by(func.randomblob(2)).limit(config.NEWEST_BOOKS)
    else:
        off = int(int(config.NEWEST_BOOKS) * (page - 1))
        entries = db.session.query(db.Books).order_by(func.randomblob(2)).offset(off).limit(config.NEWEST_BOOKS)
    pagination = Pagination(page, config.NEWEST_BOOKS, len(db.session.query(db.Books).all()))
    return render_template('discover.html', entries=entries, pagination=pagination, title=_("Random Books"))

@app.route("/language")
def language_overview():
    languages = db.session.query(db.Languages).all()

    for lang in languages:
        cur_l = LC.parse(lang.lang_code)
        lang.name = cur_l.get_language_name(get_locale())

    return render_template('languages.html', languages=languages,  title=_("Available languages"))

@app.route("/language/<name>")
def language(name):
    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    entries = db.session.query(db.Books).filter(db.Books.languages.any(db.Languages.lang_code == name )).order_by(db.Books.last_modified.desc()).all()
    cur_l = LC.parse(name)
    name = cur_l.get_language_name(get_locale())
    return render_template('index.html', random=random, entries=entries, title=_("Language: %(name)s", name=name))

@app.route("/book/<int:id>")
def show_book(id):
    entries = db.session.query(db.Books).filter(db.Books.id == id).first()
    return render_template('detail.html', entry=entries,  title=entries.title)

@app.route("/category")
def category_list():
    entries = db.session.query(db.Tags).order_by(db.Tags.name).all()
    return render_template('categories.html', entries=entries, title=_("Category list"))

@app.route("/category/<name>")
def category(name):
    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    if name != "all":
        entries = db.session.query(db.Books).filter(db.Books.tags.any(db.Tags.name.like("%" +name + "%" ))).order_by(db.Books.last_modified.desc()).all()
    else:
        entries = db.session.query(db.Books).all()
    return render_template('index.html', random=random, entries=entries, title=_("Category: %(name)s", name=name))

@app.route("/series/<name>")
def series(name):
    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    entries = db.session.query(db.Books).filter(db.Books.series.any(db.Series.name.like("%" +name + "%" ))).order_by(db.Books.series_index).all()
    return render_template('index.html', random=random, entries=entries, title=_("Series: %(name)s", name=name))


@app.route("/admin/")
def admin():
    return "Admin ONLY!"


@app.route("/search", methods=["GET"])
def search():
    term = request.args.get("query")
    if term:
        entries = db.session.query(db.Books).filter(db.or_(db.Books.tags.any(db.Tags.name.like("%"+term+"%")),db.Books.series.any(db.Series.name.like("%"+term+"%")),db.Books.authors.any(db.Authors.name.like("%"+term+"%")),db.Books.title.like("%"+term+"%"))).all()
        return render_template('search.html', searchterm=term, entries=entries)
    else:
        return render_template('search.html', searchterm="")

@app.route("/author")
def author_list():
    entries = db.session.query(db.Authors).order_by(db.Authors.sort).all()
    return render_template('authors.html', entries=entries, title=_("Author list"))

@app.route("/author/<name>")
def author(name):
    if current_user.random_books:
        random = db.session.query(db.Books).order_by(func.random()).limit(config.RANDOM_BOOKS)
    else:
        random = False

    entries = db.session.query(db.Books).filter(db.Books.authors.any(db.Authors.name.like("%" +  name + "%"))).all()
    return render_template('index.html', random=random, entries=entries, title=_("Author: %(name)s", name=name))

@app.route("/cover/<path:cover_path>")
def get_cover(cover_path):
    return send_from_directory(os.path.join(config.DB_ROOT, cover_path), "cover.jpg")

@app.route("/read/<int:book_id>")
def read_book(book_id):
    if config.USE_DL_PASS:
        if not current_user.is_authenticated():
            return app.login_manager.unauthorized()

    book = db.session.query(db.Books).filter(db.Books.id == book_id).first()
    book_dir = os.path.join(config.MAIN_DIR, "cps","static", str(book_id))
    if not os.path.exists(book_dir):
        os.mkdir(book_dir)
        for data in book.data:
            if data.format.lower() == "epub":
                zfile = zipfile.ZipFile(os.path.join(config.DB_ROOT, book.path, data.name) + ".epub")
                for name in zfile.namelist():
                    (dirName, fileName) = os.path.split(name)
                    newDir = os.path.join(book_dir, dirName)
                    if not os.path.exists(newDir):
                        os.mkdir(newDir)
                    if fileName:
                        fd = open(os.path.join(newDir, fileName), "wb")
                        fd.write(zfile.read(name))
                        fd.close()
                zfile.close()
    return render_template('read.html', bookid=book_id, title=_("Read a Book"))

@app.route("/download/<int:book_id>/<format>")
def get_download_link(book_id, format):
    if config.USE_DL_PASS:
        if not current_user.is_authenticated():
            return app.login_manager.unauthorized()

    format = format.split(".")[0]
    book = db.session.query(db.Books).filter(db.Books.id == book_id).first()
    data = db.session.query(db.Data).filter(db.Data.book == book.id).filter(db.Data.format == format.upper()).first()
    if config.USE_DL_PASS:
        helper.update_download(book_id, int(current_user.id))
    response = make_response(send_from_directory(os.path.join(config.DB_ROOT, book.path), data.name + "." +format))
    response.headers["Content-Disposition"] = "attachment; filename='%s.%s'" % (data.name, format)
    return response

@app.route('/login', methods = ['GET', 'POST'])
def login():
    error = None
    if current_user is not None and current_user.is_authenticated():
        return redirect(url_for('index'))

    if request.method == "POST":
        form = request.form.to_dict()
        user = ub.session.query(ub.User).filter(ub.User.nickname == form['username']).first()

        if user and check_password_hash(user.password, form['password']):
            login_user(user, remember = True)
            flash(_("you are now logged in as: '%(username)s'", username=user.nickname), category="success")
            return redirect(request.args.get("next") or url_for("index"))
        else:
            flash(_("Wrong Username or Password"), category="error")

    return render_template('login.html', title="login")

@app.route('/logout')
@login_required
def logout():
    if current_user is not None and current_user.is_authenticated():
        logout_user()
    return redirect(request.args.get("next") or url_for("index"))


@app.route('/send/<int:book_id>')
@login_required
def send_to_kindle(book_id):
    if current_user.kindle_mail:
        x = helper.send_mail(book_id, current_user.kindle_mail)
        if x:
            flash(_("mail successfully send to %(usermail)s", usermail=current_user.kindle_mail), category="success")
            helper.update_download(book_id, int(current_user.id))
        else:
            flash(_("there was an error sending this book"), category="error")
    else:
        flash(_("please set a kindle mail first..."), category="error")
    return redirect(request.environ["HTTP_REFERER"])

@app.route("/shelf/add/<int:shelf_id>/<int:book_id>")
@login_required
def add_to_shelf(shelf_id, book_id):
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if not shelf.is_public and not shelf.user_id == int(current_user.id):
        flash(_("Sorry you are not allowed to add a book to the the shelf: %(name)s", name=shelf.name))
        return redirect(url_for('index'))

    ins = ub.BookShelf(shelf=shelf.id, book_id=book_id)
    ub.session.add(ins)
    ub.session.commit()

    return redirect(request.environ["HTTP_REFERER"])

@app.route("/shelf/create", methods=["GET", "POST"])
@login_required
def create_shelf():
    shelf = ub.Shelf()
    if request.method == "POST":
        to_save = request.form.to_dict()
        if "is_public" in to_save:
            shelf.is_public = 1
        shelf.name = to_save["title"]
        shelf.user_id = int(current_user.id)
        try:
            ub.session.add(shelf)
            ub.session.commit()
            flash(_("Shelf %(title)s created", title=to_save["title"]), category="success")
        except:
            flash(_("there was an error"), category="error")
        return render_template('shelf_edit.html', title=_("create a shelf"))
    else:
        return render_template('shelf_edit.html', title=_("create a shelf"))

@app.route("/shelf/delete/<int:shelf_id>")
@login_required
def delete_shelf(shelf_id):
    cur_shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    deleted = 0
    if current_user.role == ub.ROLE_ADMIN:
        deleted = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).delete()

    else:
        deleted = ub.session.query(ub.Shelf).filter(ub.or_(ub.and_(ub.Shelf.user_id == int(current_user.id), ub.Shelf.id == shelf_id), ub.and_(ub.Shelf.is_public == 1, ub.Shelf.id == shelf_id))).delete()

    #ub.delete(shelf)
    if deleted:
        ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id).delete()
        ub.session.commit()
        flash( _("successfully deleted shelf %(name)s", name=cur_shelf.name, category="success") )
    return redirect(url_for('index'))

@app.route("/shelf/<int:shelf_id>")
@login_required
def show_shelf(shelf_id):
    shelf = ub.session.query(ub.Shelf).filter(ub.or_(ub.and_(ub.Shelf.user_id == int(current_user.id), ub.Shelf.id == shelf_id), ub.and_(ub.Shelf.is_public == 1, ub.Shelf.id == shelf_id))).first()
    result = list()
    if shelf:
        books_in_shelf = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id).all()
        for book in books_in_shelf:
            cur_book = db.session.query(db.Books).filter(db.Books.id == book.book_id).first()
            result.append(cur_book)

    return render_template('shelf.html', entries=result, title=_("Shelf: '%(name)s'", name=shelf.name), shelf=shelf)

@app.route("/me", methods = ["GET", "POST"])
@login_required
def profile():
    content = ub.session.query(ub.User).filter(ub.User.id == int(current_user.id)).first()
    downloads = list()
    languages = db.session.query(db.Languages).all()
    for book in content.downloads.order_by(ub.Downloads.time.desc()).all():
        downloads.append(db.session.query(db.Books).filter(db.Books.id == book.book_id).first())
    if request.method == "POST":
        to_save = request.form.to_dict()
        content.role = 0
        content.random_books = 0
        if to_save["password"]:
            content.password = generate_password_hash(to_save["password"])
        if to_save["kindle_mail"] and to_save["kindle_mail"] != content.kindle_mail:
            content.kindle_mail = to_save["kindle_mail"]
        if "user_role" in to_save and to_save["user_role"] == "on":
            content.role = 1
        if "show_random" in to_save and to_save["show_random"] == "on":
            content.random_books = 1
        if "default_language" in to_save:
            content.default_language = to_save["default_language"]
        if to_save["locale"]:
            content.locale = to_save["locale"]
        ub.session.commit()
    return render_template("user_edit.html", content=content, languages=languages, downloads=downloads, title=_("%(username)s's profile", username=current_user.nickname))

@app.route("/admin/user")
@login_required
def user_list():
    if current_user.role != ub.ROLE_ADMIN:
        return redirect(url_for('index'))
    content = ub.session.query(ub.User).all()
    return render_template("user_list.html", content=content, title=_("User list"))

@app.route("/admin/user/new", methods = ["GET", "POST"])
@login_required
def new_user():
    if current_user.role != ub.ROLE_ADMIN:
        return redirect(url_for('index'))
    content = ub.User()
    if request.method == "POST":
        to_save = request.form.to_dict()
        content.password = generate_password_hash(to_save["password"])
        content.nickname = to_save["nickname"]
        content.email = to_save["email"]
        content.kindle_mail = to_save["kindle_mail"]
        content.locale = to_save["locale"]

        if "user_role" in to_save:
            content.role = 1
        else:
            content.role = 0
        try:
            ub.session.add(content)
            ub.session.commit()
            flash(_("User created"), category="success")
        except Exception as e:
            flash(e, category="error")
    return render_template("user_edit.html", content=content, title=_("User list"))

@app.route("/admin/user/<int:user_id>", methods = ["GET", "POST"])
@login_required
def edit_user(user_id):
    if current_user.role != ub.ROLE_ADMIN:
        return redirect(url_for('index'))
    content = ub.session.query(ub.User).filter(ub.User.id == int(user_id)).first()
    downloads = list()
    for book in content.downloads.order_by(ub.Downloads.time.desc()).all():
        downloads.append(db.session.query(db.Books).filter(db.Books.id == book.book_id).first())
    if request.method == "POST":
        to_save = request.form.to_dict()
        print to_save
        if "delete" in to_save:
            ub.session.delete(content)
            return redirect(url_for('user_list'))
        else:
            if "password" in to_save:
                content.password == generate_password_hash(to_save["password"])
            if "user_role" in to_save:
                content.role = 1
            else:
                content.role = 0

            content.kindle_mail = to_save["kindle_mail"]
            content.locale = to_save["locale"]
        ub.session.commit()
        print content.password
    return render_template("user_edit.html", content=content, downloads=downloads, title=_("Edit User %(username)s" , username=current_user.nickname))

@app.route("/admin/book/<int:book_id>", methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    if current_user.role != ub.ROLE_ADMIN:
        return redirect(url_for('index'))
    ## create the function for sorting...
    db.session.connection().connection.connection.create_function("title_sort",1,db.title_sort)
    book = db.session.query(db.Books).filter(db.Books.id == book_id).first()
    if request.method == 'POST':
        to_save = request.form.to_dict()
        print to_save
        #print title_sort(to_save["book_title"])
        book.title = to_save["book_title"]
        book.authors[0].name = to_save["author_name"]

        if to_save["cover_url"] and os.path.splitext(to_save["cover_url"])[1].lower() == ".jpg":
            img = requests.get(to_save["cover_url"])
            f = open(os.path.join(config.DB_ROOT, book.path, "cover.jpg"), "wb")
            f.write(img.content)
            f.close()

        if book.series_index != to_save["series_index"]:
            book.series_index = to_save["series_index"]
        if len(book.comments):
            book.comments[0].text = to_save["description"]
        else:
            book.comments.append(db.Comments(text=to_save["description"], book=book.id))

        for tag in to_save["tags"].split(","):
            if tag.strip():
                print tag
                is_tag = db.session.query(db.Tags).filter(db.Tags.name.like('%' + tag.strip() + '%')).first()
                if is_tag:
                    book.tags.append(is_tag)
                else:
                    new_tag = db.Tags(name=tag.strip())
                    book.tags.append(new_tag)
        if to_save["series"].strip():
            is_series = db.session.query(db.Series).filter(db.Series.name.like('%' + to_save["series"].strip() + '%')).first()
            if is_series:
                book.series.append(is_series)
            else:
                new_series = db.Series(name=to_save["series"].strip(), sort=to_save["series"].strip())
                book.series.append(new_series)
        if to_save["rating"].strip():
            is_rating = db.session.query(db.Ratings).filter(db.Ratings.rating == int(to_save["rating"].strip())).first()
            if is_rating:
                book.ratings[0] = is_rating
            else:
                new_rating = db.Ratings(rating=int(to_save["rating"].strip()))
                book.ratings[0] = new_rating
        db.session.commit()
        if to_save["detail_view"]:
            return redirect(url_for('show_book', id=book.id))
        else:
            return render_template('edit_book.html', book=book)
    else:
        return render_template('edit_book.html', book=book)

@app.route('/setup', methods = ["GET", "POST"])
def setup():

    if helper.check_for_user():
        flash( _("There is already an user in your database setup is disabled. Please log in with your admin account"), category="error")
        return redirect(url_for('index'))

    user = ub.User()
    user.role = 1
    user.random_books = 1

    if request.method == "POST":
        user.random_books = 0

        to_save = request.form.to_dict()
        user.email = to_save["email"]
        user.kindle_mail == to_save["kindle_mail"]

        user.nickname = to_save["nickname"]

        if "password" in to_save and to_save["password"] != "":
            user.password = generate_password_hash(to_save["password"])

        if "locale" in to_save and to_save["locale"] != "":
            user.locale = to_save["locale"]

        if "show_random" in to_save:
            user.random_books = 1

        ub.session.merge(user)
        ub.session.commit()
        flash( _("Admin user %(username)s created!", username=user.nickname), category="success")
        return redirect(url_for('index'))

    return render_template('setup.html', content=user, title= _('Setup admin user'))


# @app.route('/admin/delete/<int:book_id>')
# def delete_book(book_id):
#     to_delete = db.session.query(db.Books).filter(db.Books.id == book_id).first()
#     print to_delete
#     db.session.delete(to_delete)
#     db.session.commit()
#     return redirect(url_for('index'))
