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
from random import randint as random

from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt5.QtWidgets import QGraphicsPixmapItem, QAction
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt5.QtWidgets import QFrame, QWidget, QFileDialog, QSplitter, QProgressBar
from PyQt5.QtGui import QPixmap, QKeySequence, QBrush, QColor
from PyQt5.QtCore import QTimer, QSize, Qt, QRectF, QMargins, QPoint

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2, GLib

import workflow
from rename_pictures import rename_file, read_image_date
import digikam

import logging
log_format = "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
# logging.basicConfig(level=logging.DEBUG, format=log_format)
logging.basicConfig(format=log_format)
logger = logging.getLogger("ananke")

# TODO:
# config file (done partially)
# properly handle reload/other dirs (compare)
# review mode

class Image:
    # see http://www.daveperrett.com/images/articles/2012-07-28-exif-orientation-handling-is-a-ghetto/EXIF_Orientations.jpg
    # WTF designed that sequence...
    # rotations as read from the metadata are strings, so these keys are too
    rotation_to_degrees = OrderedDict([
        ('1', 0),
        ('8', 90),
        ('3', 180),
        ('6', 270),
    ])

    # this *is* counter intuitive, but believe me, it's like that
    left  =  1
    right = -1


    def __init__(self, path):
        self.path = path
        self.pixmap = None
        self.metadata = None
        self.size = None
        self.zoom = None
        self.position = None
        self.action = None
        self.ignored = False


    def read(self):
        if self.pixmap is None:
            self.pixmap = QPixmap(self.path)
            try:
                self.metadata = GExiv2.Metadata(self.path)
            except GLib.Error as e:
                logger.info("Error loading %s's metadata: %s", self.path, e)
                return False

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

            return True


    def rotation(self):
        # some Android camera apps seem to set this value, I assume it's none
        if self.exif_rotation == '0':
            rotation = '1'
        else:
            rotation = self.exif_rotation

        return rotation


    def rotation_in_degrees(self):
        return self.rotation_to_degrees[self.rotation()]


    def rotate(self, where):
        rotations = list(self.rotation_to_degrees.keys())
        rotation = self.rotation()

        index = rotations.index(rotation)
        index += where
        index %= len(rotations)

        rotation = rotations[index]
        logger.debug("%s -> %s [%d]", self.exif_rotation, rotation, index)
        self.exif_rotation = rotation
        self.metadata.set_orientation(self.exif_rotation)

        try:
            self.metadata.save_file()
        except GLib.GError as e:
            # maybe the file is read only
            # no u+w support, so read the current mode, add write, then apply
            mode = os.stat(self.image.path).st.mode
            mode |= stat.S_IWUSR
            os.chmod(self.image.path, mode)

            # and try again
            self.metadata.save_file()

        self.exif_rot_to_rot()


    def exif_rot_to_rot(self):
        rotation = self.rotation_in_degrees()
        if rotation in (90, 270):
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
        logger.debug(self.index)
        if to is not None:
            self.index = to
        logger.debug(self.index)

        if how_much != 0:
            direction = how_much // abs(how_much)
            how_much = abs(how_much)
        else:
            # find the next non-deleted image
            direction = 1

        moved = 0
        logger.debug(len(self.images))
        image = self.images[self.index]

        while moved < how_much or image.ignored:
            logger.debug( (self.index, image.path, image.ignored, moved, how_much) )
            self.index += direction
            self.index %= len(self.images)

            # skip deleted images
            if not image.ignored:
                moved += 1

            image = self.images[self.index]

        logger.debug( (self.index, image.path, image.ignored, moved, how_much) )
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

            item.ignored = True

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


def catch(method):
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception as e:
            # import pdb
            # pdb.set_trace()
            import traceback
            traceback.print_exc()

    return wrapped


class Filter(QWidget):
    label_map = { 'K': 'Keep', 'T': 'Take', 'S': 'Stitch', 'M': 'Compare',
                  'C': 'Crop', 'D': 'Delete', None: '' }

    # see https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L8128
    multiple_exposure_map = {
        '0': 'Off',
        # '1': 'Multiple Exposure',
        '1': 'Manual',
        '2': 'Image Overlay',
        '3': 'HDR',
    }

    active_dlightning_map = {
            '0': 'Off',
        '65535': 'Auto',
            '7': 'Extra High',
            '5': 'High',
            '3': 'Normal',
            '1': 'Low',
    }

    def __init__(self, parent, config, new_files):
        QWidget.__init__(self, parent)
        self.zoom_level = 1.0
        self.rotation = 0

        self.all_images = ImageList()
        self.compare_set = ImageList()
        self.tagged_count = 0
        # start with all images
        self.images = self.all_images
        self.comparing = False
        self.random = False

        self.buildUI(parent)

        self.src = config['Directories']['mid']
        self.dst = os.getcwd()
        self.scan(self.src)
        self.new_files = new_files

        self.image = None

        self.image_actions = defaultdict(lambda: None)
        self.image_positions = {}
        self.original_position = None

        self.dir_dialog = QFileDialog(self)
        self.dir_dialog.setFileMode(QFileDialog.Directory)
        self.dir_dialog.modal = False
        self.dir_dialog.setOption(QFileDialog.ShowDirsOnly)
        self.dir_dialog.setAcceptMode(QFileDialog.AcceptSave)


    @catch
    def toggle_random(self, *args):
        self.random = not self.random


    def buildUI(self, parent):
        # left labels
        self.splitter = QSplitter(self)
        self.splitter.setContentsMargins(QMargins(0, 0, 0, 0))
        self.splitter.setOrientation(Qt.Horizontal)

        self.widget = QWidget(self.splitter)
        self.label_layout = QVBoxLayout(self.widget)
        self.label_layout.setSpacing(0)

        for name in [ 'date', 'size', 'focal_length', 'focal_length_35mm_equivalent',
                      'exposure_time', 'fnumber', 'iso_speed', 'focus', 'focus_distance',
                      'exposure_compensation', 'multiple_exposure', 'multiple_exposure_shots',
                      'active_dlightning', 'white_balance', 'picture_control',
                      'noise_reduction', 'rating']:
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

        # progress bar, hidden initially
        self.pbar = QProgressBar(self)
        self.pbar.setFormat("%v / %m")
        # TODO:
        # sp = QSizePolicy(
        # self.pbar.hide()

        status_bar = QHBoxLayout()
        status_bar.addWidget(self.fname)
        status_bar.addItem(spacer)
        status_bar.addWidget(self.tag_view)
        status_bar.addWidget(self.pbar)

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
        for key, slot in (
                (Qt.Key_Home,      self.first_image),
                (Qt.CTRL + Qt.Key_PageUp,   self.prev_hundred),
                (Qt.Key_PageUp,    self.prev_ten),
                (Qt.Key_Backspace, self.prev_image),
                (Qt.Key_Space,     self.next_image),
                (Qt.Key_PageDown,  self.next_ten),
                (Qt.CTRL + Qt.Key_PageDown, self.next_hundred),
                (Qt.Key_End,       self.last_image),
                (Qt.CTRL + Qt.Key_R, self.toggle_random),

                (Qt.Key_Greater, self.rotate_right),
                (Qt.Key_Less,    self.rotate_left),
                (Qt.Key_F,       self.toggle_fullsize),

                (Qt.Key_K, self.keep),
                (Qt.Key_T, self.tag),
                (Qt.Key_S, self.stitch),
                (Qt.Key_M, self.select_for_compare),
                (Qt.Key_C, self.crop),
                (Qt.CTRL + Qt.Key_D, self.delete),
                (Qt.Key_U, self.untag),
                (Qt.CTRL + Qt.Key_X, self.expunge),
                (Qt.Key_Return, self.apply),

                (Qt.CTRL + Qt.Key_M, self.compare),
                (Qt.CTRL + Qt.Key_O, self.new_src),
                (Qt.CTRL + Qt.Key_S, self.save),

                (Qt.Key_0, lambda *ignore: self.set_rating(-1)),
                (Qt.Key_1, lambda *ignore: self.set_rating( 1)),
                (Qt.Key_2, lambda *ignore: self.set_rating( 2)),
                (Qt.Key_3, lambda *ignore: self.set_rating( 3)),
                (Qt.Key_4, lambda *ignore: self.set_rating( 4)),
                (Qt.Key_5, lambda *ignore: self.set_rating( 5)),
            ):

            action = QAction(parent)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.view.addAction(action)


    @catch
    def set_rating(self, rating):
        name = os.path.basename(self.image.path)
        image = digikam.image(name)

        if image is not None:
            logger.debug("%s: %d", name, image.info[0].rating)
            image.info[0].rating = rating
            digikam.session.commit()

            self.update_rating(name)


    @catch
    def scan(self, src):
        logger.debug('scanning %r', src)

        total = 0
        count = 0

        for r, dirs, files in os.walk(os.path.abspath(src)):
            total += len(files)
            self.pbar.setRange(1, total)

            for name in files:
                count += 1
                self.pbar.setValue(count)

                if name[-4:].lower() in ('.jpg', '.png'):
                    # logger.info('found %s',  name)
                    self.images.add(Image(os.path.join(r, name)))

        self.pbar.reset()


    @catch
    def rotate_view(self):
        # we have to 'undo' the rotations, so the numbers are negative
        rotate = -self.image.rotation_in_degrees()

        # undo the last rotation and apply the new one
        self.view.rotate(-self.rotation + rotate)
        self.rotation = rotate
        logger.debug( (rotate, self.rotation) )


    @catch
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


    @catch
    def zoom(self, zoom_level):
        # logger.info(zoom_level)
        scale = zoom_level/self.zoom_level
        # logger.info("scaling", scale)
        self.view.scale(scale, scale)

        self.zoom_level = zoom_level


    @catch
    def move_index(self, to=None, how_much=0):
        # images might fail to load (for instance, the file was removed
        # while we were running, and we don't have inotify support yet)
        # so also iterate until we can find one that loads
        print(f"{to}:{how_much}")
        finished = to is None and how_much == 0

        while not finished:
            if self.image is not None:
                self.save_position()
                self.image.release()

            if not self.random:
                index = self.images.move_index(to, how_much)
            else:
                to = random(0, len(self.images) - 1)
                index = self.images.move_index(to)

            self.image = self.images.current_image
            finished = self.image.read()

            if not finished:
                self.image.ignored = True

            logger.info((self.image.path, finished))



        self.show_image()


    @catch
    def view_position(self):
        view_size = self.view.size()
        center = QPoint(view_size.width() // 2, view_size.height() // 2)
        position = self.view.mapToScene(center)

        return position


    @catch
    def show_image(self):
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


    @catch
    def update_view(self):
        self.fname.setText(self.image.path)
        label = self.label_map[self.image.action]
        self.tag_view.setText(label)

        meta = self.image.metadata

        date = read_image_date(self.image.path, meta)
        if date is None:
            self.date.setText('Unknown')
        else:
            self.date.setText(date.isoformat())

        size = f"{meta.get_metadata_pixel_width()}px x {meta.get_metadata_pixel_height()}px"
        self.size.setText(size)

        # get_focal_length() returns a float, so int() first, then str()
        self.focal_length.setText(f"{int(meta.get_focal_length())}mm")

        # OTOH, Exif.Photo.FocalLengthIn35mmFilm returns a str() already
        value = meta.get('Exif.Photo.FocalLengthIn35mmFilm', 'Unknown')
        self.focal_length_35mm_equivalent.setText(f"{value}mm")

        f = meta.get_exposure_time()
        if f is None:
            s = 'unknown'
        elif f.denominator == 1:
            s = f"{f.numerator}s"
        else:
            s = f"{f.numerator}/{f.denominator}s"
        self.exposure_time.setText(s)

        self.fnumber.setText(f"f/{meta.get_fnumber()}")

        self.iso_speed.setText(f"ISO {meta.get_iso_speed()}")

        self.focus.setText(meta.get('Exif.Nikon3.Focus', 'N/A').strip())

        try:
            distance = int(meta['Exif.NikonLd3.FocusDistance'])
        except KeyError:
            self.focus_distance.setText('None')
        else:
            # see https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L4235
            value_conv = 0.01 * 10 ** (distance / 40)
            self.focus_distance.setText(f"{value_conv:.1f}m")

        try:
            stops = Fraction(meta['Exif.Photo.ExposureBiasValue'])
        except (KeyError, ZeroDivisionError):
            self.exposure_compensation.setText('None')
        else:
            self.exposure_compensation.setText(f"{stops} stops")

        value = meta.get('Exif.Nikon3.ActiveDLighting', '0')
        self.active_dlightning.setText(self.active_dlightning_map[value])

        # multi exposure
        # https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L8118
        # incoming/01-tmp/2020-11-06T22.58.14.jpg  Exif.NikonMe.MultiExposureMode               Long        1  (3)
        # incoming/01-tmp/2020-11-06T22.58.14.jpg  Exif.NikonMe.MultiExposureShots              Long        1  2
        value = meta.get('Exif.NikonMe.MultiExposureMode', '0')
        self.multiple_exposure.setText(self.multiple_exposure_map[value])

        value = meta.get('Exif.NikonMe.MultiExposureShots', 'N/A')
        self.multiple_exposure_shots.setText(value)

        # hdr
        # https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L8144
        # value = meta.get('', 'N/A')
        # self.hdr.setText(value)

        # exposure time
        # https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L8266
        # https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Nikon.pm#L8371

        value = self.get_value(meta, [ 'Exif.Nikon3.WhiteBalance', 'Exif.CanonPr.WhiteBalance' ],'Unknown')
        self.white_balance.setText(value)
        # Exif.Nikon3.WhiteBalanceBias

        value = meta.get('Exif.NikonPc.Name', 'Unknown').strip().capitalize()
        self.picture_control.setText(value)

        value = meta.get('Exif.Nikon3.NoiseReduction', 'Unknown').strip().capitalize()
        self.noise_reduction.setText(value)

        self.update_rating()


    @catch
    def update_rating(self, name=None):
        if name is None:
            name = os.path.basename(self.image.path)

        image = digikam.image(name)
        if image is not None:
            self.rating.setText(str(image.info[0].rating))
        else:
            self.rating.setText('N/A')


    @catch
    def save_position(self):
        position = self.view_position()
        if (   self.original_position is None
            or position.x() != self.original_position.x()
            or position.y() != self.original_position.y()):

            logger.debug("saving position: %f x %f", position.x(), position.y())
            # this way (I hope) I only remember those positions which changed
            self.image_positions[self.image.path] = position


    # movements
    @catch
    def first_image(self, *args):
        self.move_index(to=0)

    @catch
    def prev_hundred(self, *args):
        self.move_index(how_much=-100)

    @catch
    def prev_ten(self, *args):
        self.move_index(how_much=-10)

    @catch
    def prev_image(self, *args):
        self.move_index(how_much=-1)

    @catch
    def next_image(self, *args):
        self.move_index(how_much=+1)

    @catch
    def next_ten(self, *args):
        self.move_index(how_much=+10)

    @catch
    def next_hundred(self, *args):
        self.move_index(how_much=+100)

    @catch
    def last_image(self, *args):
        self.move_index(to=len(self.images)-1)


    @catch
    def toggle_fullsize(self, *args):
        # noooooooooooooooothing compares...
        if abs(self.zoom_level - 1.0) < 0.000001:
            # logger.info('fit')
            self.zoom_to_fit()
        else:
            # logger.info('orig')
            self.zoom(1.0)


    @catch
    def rotate_left(self, *args):
        self.image.rotate(Image.left)
        self.show_image()


    @catch
    def rotate_right(self, *args):
        self.image.rotate(Image.right)
        self.rotate_view()


    # image actions
    # Keep -> /gallery/foo, resized
    @catch
    def keep(self, *args):
        self.image.action = 'K'
        self.tagged_count += 1
        self.next_image()


    # Tag -> /gallery/foo, as-is
    @catch
    def tag(self, *args):
        self.image.action = 'T'
        self.tagged_count += 1
        self.next_image()


    # Stitch -> 02-new/stitch
    @catch
    def stitch(self, *args):
        self.image.action = 'S'
        self.tagged_count += 1
        self.next_image()


    # coMpare
    @catch
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


    @catch
    def compare(self, *args):
        logger.info('comparing')
        self.comparing = True
        self.images = self.compare_set
        self.move_index(to=0)


    # Crop -> launch gwenview
    @catch
    def crop(self, *args):
        self.image.action = 'C'
        self.tagged_count += 1
        self.next_image()


    # Delete -> /dev/null
    @catch
    def delete(self, *args):
        self.image.action = 'D'
        self.tagged_count += 1
        logger.info("[%d] %s marked for deletion", self.images.index, self.image.path)

        if self.comparing:
            # remove the image from the list and refresh the view
            self.images.remove()
            self.image = self.images.current_image
            self.show_image()
        else:
            self.next_image()


    @catch
    def untag(self, *args):
        try:
            self.image.action = None
            # don't move, most probably I'm reconsidering what to do
            # but change the label
            self.tag_view.setText('')
            self.tagged_count -= 1
        except KeyError:
            # tried to untag a non-tagged image
            pass


    @catch
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


    @catch
    def apply(self, *args):
        if not self.comparing:
            done_count = 0
            self.pbar.setRange(1, self.tagged_count)

            hugin = False

            if len([ img.action for img in self.images if img.action in ('K', 'T') ]) > 0:
                self.new_dst()

            for index, img in enumerate(self.images):  # already sorted by fname
                if img.ignored:
                    continue

                src = img.path
                dst = os.path.join(self.dst, os.path.basename(src))
                action = img.action

                if action is not None:
                    logger.debug((src, dst, action))

                try:
                    if src in self.new_files and action not in ('C', 'D'):
                        # rename
                        src = rename_file(src)

                    if   action == 'K':
                        # Keep -> /gallery/foo, as-is
                        logger.info("%s -> %s", src, dst)
                        shutil.move(src, dst)

                        done_count += 1
                        self.pbar.setValue(done_count)

                    elif action == 'T':
                        # Take -> /gallery/foo, resized
                        self.resize(src, dst)

                        done_count += 1
                        self.pbar.setValue(done_count)

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
                        os.system('gwenview %s' % src)

                        # asume the file was saved under a new name
                        # logger.info("%s -> %s", src, dst)
                        # shutil.move(src, dst)

                        done_count += 1
                        self.pbar.setValue(done_count)

                    elif action == 'D':
                        # Delete -> /dev/null
                        os.unlink(src)
                        logger.info("%s deleted", src)

                        done_count += 1
                        self.pbar.setValue(done_count)

                    if action in ('K', 'T', 'D', 'C', 'S'):
                        # don't show the image anymore
                        logger.debug("%s ignored", img)
                        img.ignored = True

                except FileNotFoundError as e:
                    logger.info(e)

            if hugin:
                os.system('hugin')

            self.tagged_count = 0

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


    @catch
    def expunge(self, *args):
        for img in self.images:
            src = img.path
            try:
                if img.action == 'D':
                    # Delete -> /dev/null
                    os.unlink(src)
                    self.images.remove(img)
                    img.ignored = True
                    logger.info("%s deleted", src)

                    # we don't really remove images, just mark them as so
                    # so remove the action
                    img.action = None
            except FileNotFoundError as e:
                logger.info(e)


    @catch
    def reset(self, new_root=None):
        if new_root is not None:
            self.src = new_root

        self.image_actions.clear()
        self.compare_set.clear()
        self.comparing = False

        self.pbar.reset()


    @catch
    def new_dst(self, *args):
        self.dir_dialog.setDirectory(self.dst)
        if self.dir_dialog.exec():
            self.dst = self.dir_dialog.selectedFiles()[0]


    @catch
    def new_src(self, *args):
        self.dir_dialog.setDirectory(self.src)
        if self.dir_dialog.exec():
            self.src = self.dir_dialog.selectedFiles()[0]
            self.reset()


    @catch
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

            self.image.ignored = True
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
    show_first_image = QTimer.singleShot(200, view.first_image)

    win.setCentralWidget(view)
    win.showFullScreen()

    app.exec_()
