#! /usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2016 Marcos Dione <mdione@grulic.org.ar>
# In ancient Greek religion, Ananke (Ἀνάγκη) is a personification of
# inevitability, compulsion and necessity.

import os
import os.path
import sys
from collections import defaultdict, OrderedDict
import shutil
from configparser import ConfigParser
from bisect import insort, bisect_left
from fractions import Fraction

from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt5.QtWidgets import QGraphicsPixmapItem, QAction
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt5.QtWidgets import QFrame, QWidget, QFileDialog, QSplitter
from PyQt5.QtGui import QPixmap, QKeySequence, QBrush, QColor
from PyQt5.QtCore import QTimer, QSize, Qt, QRectF, QMargins, QPoint

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2, GLib

import workflow
from rename_pictures import rename_file, read_image_date

import logging
log_format = "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
# logging.basicConfig(level=logging.DEBUG, format=log_format)
logging.basicConfig(format=log_format)
logger = logging.getLogger("ananke")

# TODO:
# config file (done partially)
# properly handle reload/other dirs (compare)

class Image:
    # see http://www.daveperrett.com/images/articles/2012-07-28-exif-orientation-handling-is-a-ghetto/EXIF_Orientations.jpg
    # rotations as read from the metadata are strings
    rotation_to_degrees = OrderedDict([
        ('1', 0),
        ('8', 90),
        ('3', 180),
        ('6', 270)
    ])

    # this is counter intuitive, but believe me, it's like that
    left  =  1
    right = -1


    def __init__(self, path):
        self.path = path
        self.pixmap = None
        self.metadata = None
        self.size = None
        self.rotation = None
        self.zoom = None
        self.position = None
        self.action = None
        self.deleted = False


    def read(self):
        if self.pixmap is None:
            self.pixmap = QPixmap(self.path)
            self.metadata = GExiv2.Metadata(self.path)

            # the view will need three parameters:
            # rotation
            # size
            # zoom
            # the first is needed to properly orient the view over the scene
            # the other two are needed for zoom, mostly
            # but the rotation defines the images size, so they're linked
            self.size = self.pixmap.size()

            try:
                # try directly to get the tag, because sometimes get_tags() returns
                # tags that don't actually are in the file

                # this implicitly loads the metadata
                self.exif_rotation = self.metadata['Exif.Image.Orientation']
            except KeyError:
                # guess :-/
                logger.info("exif_rotation 'guessed'")
                self.exif_rotation = '1'

            self.exif_rot_to_rot()

            self.zoom


    def rotate(self, where):
        index = list(self.rotation_to_degrees.keys()).index(self.exif_rotation)
        index += where
        index %= 4

        self.exif_rotation = list(self.rotation_to_degrees.keys())[index]
        self.metadata.set_orientation(self.exif_rotation)
        self.metadata.save_file()
        self.exif_rot_to_rot()


    def exif_rot_to_rot(self):
        self.rotation = self.rotation_to_degrees[self.exif_rotation]
        if self.rotation in (90, 270):
            self.size = QSize(self.size.height(), self.size.width())


    def release(self):
        """Stop referencing the QPixmap object so its memory is released."""
        self.pixmap = None


    def __lt__(self, other):
        return self.path < other.path


class ImageList:
    """A list of Images with a cursor."""
    def __init__(self):
        self.images = []
        self.index = 0
        self.current_image = None


    def move_index(self, to=None, how_much=0):
        if to is not None:
            self.index = to

        if how_much != 0:
            direction = how_much // abs(how_much)
            how_much = abs(how_much)
        else:
            # move forward
            direction = 1

        moved = 0
        image = self.images[self.index]

        while moved < how_much or image.deleted:
            logger.debug( (self.index, image.path, image.deleted, moved, how_much) )
            self.index += direction
            self.index %= len(self.images)

            # skip deleted images
            if not image.deleted:
                moved += 1

            image = self.images[self.index]

        logger.debug( (self.index, image.path, image.deleted, moved, how_much) )
        self.current_image = image


    def add(self, image):
        insort(self.images, image)


    def remove(self, item=None):
        """Remove the current image from the list or the given item."""
        if item is None:
            index = self.index
        else:
            index = bisect_left(self.images, item)
            if self.images[index] != item:
                raise ValueError

        self.images[index].deleted = True
        logger.debug( (index, self.images[index].path) )
        self.move_index()


    def clear(self):
        self.images.clear()


    def __len__(self):
        return len(self.images)


    def __getitem__(self, index):
        return self.images[index]


    def __iter__(self):
        return ( image for image in self.images if image is not None )


class Filter(QWidget):
    label_map = { 'K': 'Keep', 'T': 'Take', 'S': 'Stitch', 'M': 'Compare',
                  'C': 'Crop', 'D': 'Delete', None: '' }

    def __init__(self, parent, config, new_files):
        QWidget.__init__(self, parent)
        self.zoom_level = 1.0
        self.rotation = 0

        self.all_images = ImageList()
        self.compare_set = ImageList()
        # start with all images
        self.images = self.all_images
        self.comparing = False

        self.src = config['Directories']['mid']
        self.dst = os.getcwd()
        self.scan(self.src)
        self.new_files = new_files

        self.image = None

        self.image_actions = defaultdict(lambda: None)
        self.image_positions = {}
        self.original_position = None

        self.buildUI(parent)

        self.dir_dialog = QFileDialog(self)
        self.dir_dialog.setFileMode(QFileDialog.Directory)
        self.dir_dialog.modal = False
        self.dir_dialog.setOption(QFileDialog.ShowDirsOnly)
        self.dir_dialog.setAcceptMode(QFileDialog.AcceptSave)


    def buildUI(self, parent):
        # left labels
        self.splitter = QSplitter(self)
        self.splitter.setContentsMargins(QMargins(0, 0, 0, 0))
        self.splitter.setOrientation(Qt.Horizontal)

        self.widget = QWidget(self.splitter)
        self.label_layout = QVBoxLayout(self.widget)

        for name in [ 'size', 'exposure_time', 'fnumber', 'iso_speed', 'focal_length',
                      'date', 'active_dlightning', 'exposure_compensation']:
            key_label = QLabel(name.replace('_', ' ').title(), self.widget)
            self.label_layout.addWidget(key_label)

            value_label = QLabel(self.widget)
            value_label.setAlignment(Qt.AlignRight)
            setattr(self, name, value_label)
            self.label_layout.addWidget(value_label)

        # TODO
        s = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.label_layout.addItem(s)

        # main view
        self.scene = QGraphicsScene()

        self.pixmap_view = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_view)

        self.view = QGraphicsView(self.scene, parent)
        self.view.setFrameShadow(QFrame.Plain)
        self.view.setFrameStyle(QFrame.NoFrame)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy  (Qt.ScrollBarAlwaysOff)

        brush = QBrush(QColor(20, 20, 20))
        brush.setStyle(Qt.SolidPattern)
        self.view.setBackgroundBrush(brush)

        self.view.show()

        # "status bar"
        self.fname = QLabel(self)
        self.fname.setTextInteractionFlags(Qt.TextSelectableByMouse)
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.tag_view = QLabel(self)

        status_bar = QHBoxLayout()
        status_bar.addWidget(self.fname)
        status_bar.addItem(spacer)
        status_bar.addWidget(self.tag_view)

        w = QWidget(self.splitter)

        v = QVBoxLayout(w)
        v.setContentsMargins(QMargins(0, 0, 0, 0))
        v.addWidget(self.view)
        v.addLayout(status_bar)

        self.splitter.setSizes([165, 1435])

        h = QHBoxLayout(self)
        h.setContentsMargins(QMargins(0, 0, 0, 0))
        h.addWidget(self.splitter)

        # now... ACTION!(s)
        for key, slot in ((Qt.Key_Home,      self.first_image),
                          (Qt.Key_PageUp,    self.prev_ten),
                          (Qt.Key_Backspace, self.prev_image),
                          (Qt.Key_Space,     self.next_image),
                          (Qt.Key_PageDown,  self.next_ten),
                          (Qt.Key_End,       self.last_image),

                          (Qt.Key_Greater, self.rotate_right),
                          (Qt.Key_Less,    self.rotate_left),
                          (Qt.Key_F,       self.toggle_fullsize),

                          (Qt.Key_K, self.keep),
                          (Qt.Key_T, self.tag),
                          (Qt.Key_S, self.stitch),
                          (Qt.Key_M, self.select_for_compare),
                          (Qt.Key_C, self.crop),
                          (Qt.Key_D, self.delete),
                          (Qt.Key_U, self.untag),
                          (Qt.Key_X, self.expunge),
                          (Qt.Key_Return, self.apply),

                          (Qt.CTRL+Qt.Key_M, self.compare),
                          (Qt.CTRL+Qt.Key_O, self.new_src),
                          (Qt.CTRL+Qt.Key_S, self.save),):
            action = QAction(parent)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.view.addAction(action)


    def scan(self, src):
        logger.debug('scanning %r', src)
        for r, dirs, files in os.walk(os.path.abspath(src)):
            for name in files:
                if name[-4:].lower() in ('.jpg', '.png'):
                    # logger.info('found %s',  name)
                    self.images.add(Image(os.path.join(r, name)))


    def rotate_view(self):
        # we have to 'undo' the rotations, so the numbers are negative
        rotate = -self.image.rotation

        # undo the last rotation and apply the new one
        self.view.rotate(-self.rotation+rotate)
        self.rotation = rotate
        logger.debug( (rotate, self.rotation) )


    def zoom_to_fit(self):
        win_size = self.view.size()
        logger.debug( (self.image.size, win_size, self.image.path) )

        try:
            hZoom = win_size.width() / self.image.size.width()
            vZoom = win_size.height() / self.image.size.height()
            zoom_level = min(hZoom, vZoom)
        except ZeroDivisionError:
            zoom_level = 1

        self.zoom(zoom_level)


    def zoom(self, zoom_level):
        # logger.info(zoom_level)
        scale = zoom_level/self.zoom_level
        # logger.info("scaling", scale)
        self.view.scale(scale, scale)

        self.zoom_level = zoom_level


    def move_index(self, to=None, how_much=0):
        if self.image is not None:
            self.save_position()

        self.images.move_index(to, how_much)

        self.image = self.images.current_image
        self.show_image()


    def view_position(self):
        view_size = self.view.size()
        center = QPoint(view_size.width()/2, view_size.height()/2)
        position = self.view.mapToScene(center)
        return position


    def show_image(self):
        logger.info(self.image.path)
        self.image.read()

        self.rotate_view()
        self.pixmap_view.setPixmap(self.image.pixmap)
        if self.zoom_level != 1.0:
            self.zoom_to_fit()

        # we might have rotated the view, but the scene still has the image
        # in its original size, so we use that as bounding rect
        boundingRect = QRectF(self.pixmap_view.pixmap().rect())
        logger.debug(boundingRect)
        self.scene.setSceneRect(boundingRect)

        if self.image.path in self.image_positions:
            self.original_position = None
            position = self.image_positions[self.image.path]
            logger.debug("previously moved, back to that point: %f x %f", position.x(), position.y())
            self.view.centerOn(position)
        else:
            # TODO: 'undo' the move
            position = self.view_position()
            logger.debug("original position: %f x %f", position.x(), position.y())
            self.original_position = position
            self.view.centerOn(self.pixmap_view)

        self.update_view()


    def update_view(self):
        self.fname.setText(self.image.path)
        label = self.label_map[self.image.action]
        self.tag_view.setText(label)

        meta = self.image.metadata

        size = "%d x %d" % (meta.get_metadata_pixel_width(),
                            meta.get_metadata_pixel_height())
        self.size.setText(size)

        date = read_image_date(self.image.path, meta)
        if date is None:
            self.date.setText('unknown')
        else:
            self.date.setText(date.isoformat())

        self.fnumber.setText(str(meta.get_fnumber()))
        self.focal_length.setText(str(meta.get_focal_length()))
        self.iso_speed.setText(str(meta.get_iso_speed()))

        f = meta.get_exposure_time()
        if f is None:
            s = 'unknown'
        elif f.denominator == 1:
            s = '%ds' % f.numerator
        else:
            s = '%d/%ds' % (f.numerator, f.denominator)
        self.exposure_time.setText(s)

        try:
            self.active_dlightning.setText(meta['Exif.Nikon3.ActiveDLighting'])
        except KeyError:
            self.active_dlightning.setText('None')

        try:
            stops = Fraction(meta['Exif.Photo.ExposureBiasValue'])
        except (KeyError, ZeroDivisionError):
            self.exposure_compensation.setText('None')
        else:
            self.exposure_compensation.setText(str(stops))

        # Exif.Nikon3.WhiteBalance
        # Exif.Nikon3.WhiteBalanceBias
        # Exif.Nikon3.Focus


    def save_position(self):
        position = self.view_position()
        if (   self.original_position is None
            or position.x() != self.original_position.x()
            or position.y() != self.original_position.y()):

            logger.debug("saving position: %f x %f", position.x(), position.y())
            # this way (I hope) I only remember those positions which changed
            self.image_positions[self.image.path] = position


    # movements
    def first_image(self, *args):
        self.move_index(to=0)

    def prev_ten(self, *args):
        self.move_index(how_much=-10)

    def prev_image(self, *args):
        self.move_index(how_much=-1)

    def next_image(self, *args):
        self.move_index(how_much=+1)

    def next_ten(self, *args):
        self.move_index(how_much=+10)

    def last_image(self, *args):
        self.move_index(to=len(self.images)-1)


    def toggle_fullsize(self, *args):
        # noooooooooooooooothing compares...
        if abs(self.zoom_level - 1.0) < 0.000001:
            # logger.info('fit')
            self.zoom_to_fit()
        else:
            # logger.info('orig')
            self.zoom(1.0)


    def rotate_left(self, *args):
        self.image.rotate(Image.left)
        self.rotate_view()


    def rotate_right(self, *args):
        self.image.rotate(Image.right)
        self.rotate_view()


    # image actions
    # Keep -> /gallery/foo, resized
    def keep(self, *args):
        self.image.action = 'K'
        self.next_image()


    # Tag -> /gallery/foo, as-is
    def tag(self, *args):
        self.image.action = 'T'
        self.next_image()


    # Stitch -> 02-new/stitch
    def stitch(self, *args):
        self.image.action = 'S'
        self.next_image()


    # coMpare
    def select_for_compare(self, *args):
        if self.image.action == 'M':
            # TODO?: undo/toggle
            # NOTE: this can already be achieved by Untag
            pass
        else:
            self.image.action = 'M'
            # ugh
            self.compare_set.add(self.image)
            logger.debug(self.compare_set.images)

        self.next_image()


    def compare(self):
        logger.info('comparing')
        self.comparing = True
        self.images = self.compare_set
        self.move_index()

    # Crop -> launch gwenview
    def crop(self, *args):
        self.image.action = 'C'
        self.next_image()


    # Delete -> /dev/null
    def delete(self, *args):
        self.image.action = 'D'
        logger.info("[%d] %s marked for deletion", self.images.index, self.image.path)

        if self.comparing:
            # remove the image from the list and refresh the view
            self.images.remove()
            self.image = self.images.current_image
            self.show_image()
        else:
            self.next_image()


    def untag(self, *args):
        try:
            self.image.action = None
            # don't move, most probably I'm reconsidering what to do
            # but change the label
            self.tag_view.setText('')
        except KeyError:
            # tried to untag a non-tagged image
            pass


    def resize(self, src, dst):
        src_meta = GExiv2.Metadata(src)
        src_p = QPixmap(src)
        dst_p = src_p.scaled(4500, 3000, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)

        dst_p.save(src)
        shutil.move(src, dst)

        # copy all the metadata
        dst_meta = GExiv2.Metadata(dst)
        for tag in src_meta.get_tags():
            dst_meta[tag] = src_meta[tag]

        dst_meta.save_file()


    def apply(self, *args):
        if not self.comparing:
            hugin = False

            if len([ img.action for img in self.images if img.action in ('K', 'T') ]) > 0:
                self.new_dst()

            for index, img in enumerate(self.images):  # already sorted by fname
                src = img.path
                dst = os.path.join(self.dst, os.path.basename(src))
                action = img.action

                try:
                    if src in self.new_files and action not in ('C', 'D'):
                        # rename
                        src = rename_file(src)

                    if   action == 'K':
                        # Keep -> /gallery/foo, as-is
                        logger.info("%s -> %s", src, dst)
                        shutil.move(src, dst)

                    elif action == 'T':
                        # Tag -> /gallery/foo, resized
                        self.resize(src, dst)

                    elif action == 'S':
                        # Stitch -> 02-new/stitch
                        dst = os.path.join('/home/mdione/Pictures/incoming/02-new/stitch',
                                           os.path.basename(src))
                        logger.info("%s -> %s", src, dst)
                        shutil.move(src, dst)
                        hugin = True

                    elif action == 'M':
                        # coMpare -> 03-cur
                        dst = os.path.join('/home/mdione/Pictures/incoming/03-cur',
                                           os.path.basename(src))
                        logger.info("%s -> %s", src, dst)
                        shutil.move (src, dst)

                        new_root = '/home/mdione/Pictures/incoming/03-cur'
                        old_root = self.src

                    elif action == 'C':
                        # Crop -> launch gwenview
                        os.system('gwenview %s', src)

                        # asume the file was saved under a new name
                        # logger.info("%s -> %s", src, dst)
                        # shutil.move(src, dst)


                    elif action == 'D':
                        # Delete -> /dev/null
                        os.unlink(src)
                        logger.info("%s deleted", src)
                        # mark as non existing, move_index() will skip these
                        # TODO:
                        self.images.remove(img)
                except FileNotFoundError as e:
                    logger.info(e)

            if hugin:
                os.system('hugin')

            self.reset()
        else:
            logger.info('back to all')
            self.comparing = False

            # untag all images marked for compare
            for image in self.compare_set:
                # but only those still marked 'M'
                if image.action == 'M':
                    image.action = None

            self.compare_set.clear()
            self.images = self.all_images
            self.move_index()


    def expunge(self, *args):
        for img in self.images:
            src = img.path
            try:
                if img.action == 'D':
                    # Delete -> /dev/null
                    os.unlink(src)
                    logger.info("%s deleted", src)
                    self.images.remove(img)

                    # we don't really remove images, just mark them as so
                    # so remove the action
                    img.action = None
            except FileNotFoundError as e:
                logger.info(e)

        self.reset()


    def reset(self, new_root=None):
        if new_root is not None:
            self.src = new_root

        self.image_actions.clear()
        self.all_images.clear()
        self.compare_set.clear()
        self.comparing = False
        self.scan(self.src)


    def new_dst(self, *args):
        self.dir_dialog.setDirectory(self.dst)
        if self.dir_dialog.exec():
            self.dst = self.dir_dialog.selectedFiles()[0]


    def new_src(self, *args):
        self.dir_dialog.setDirectory(self.src)
        if self.dir_dialog.exec():
            self.src = self.dir_dialog.selectedFiles()[0]
            self.reset()


    def save(self, *args):
        src = self.image.path
        self.dir_dialog.setDirectory(self.dst)
        if self.dir_dialog.exec():
            dst_dir = self.dir_dialog.selectedFiles()[0]
            if src in self.new_files:
                src = rename_file(src)

            dst = os.path.join(dst_dir, os.path.basename(src))

            logger.info("%s -> %s", src, dst)
            self.resize(src, dst)

            self.next_image()


if __name__ == '__main__':
    config =  ConfigParser()
    config.read('ananke.ini')

    app = QApplication(sys.argv)

    # import
    src = config['Directories']['src']
    mid = config['Directories']['mid']
    new = workflow.import_files(src, mid)

    win = QMainWindow()

    view = Filter(win, config, new)
    firstImage = QTimer.singleShot(200, view.first_image)

    win.setCentralWidget(view)
    win.showFullScreen()

    app.exec_()
