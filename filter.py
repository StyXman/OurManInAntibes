#! /usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2016 Marcos Dione <mdione@grulic.org.ar>
# In ancient Greek religion, Ananke (/əˈnæŋkiː/) is a personification of
# inevitability, compulsion and necessity.

import os
import os.path
import sys
from collections import defaultdict
import shutil
from configparser import ConfigParser

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
from rename_pictures import rename_file

import logging
log_format= "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
logging.basicConfig (level=logging.DEBUG, format=log_format)
logger= logging.getLogger ("ananke")

# TODO:
# config file (done partially)
# properly handle reload/other dirs (compare)
# compare by just navigating through selected images
# save w/ resize
# rotate

class Image:
    # see http://www.daveperrett.com/images/articles/2012-07-28-exif-orientation-handling-is-a-ghetto/EXIF_Orientations.jpg
    # rotations as read from the metadata are strings
    rotation_to_degrees = {
        '1': 0,
        '8': 90,
        '3': 180,
        '6': 270
    }

    def __init__(self, path):
        self.path = path
        self.pixmap = None
        self.metadata = None
        self.size = None
        self.rotation = None
        self.zoom = None
        self.position = None


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
                rot = self.metadata['Exif.Image.Orientation']
            except KeyError:
                # guess :-/
                logger.info("rotation 'guessed'")
                rot = '1'

            self.rotation = self.rotation_to_degrees[rot]
            if self.rotation in (90, 270):
                self.size = QSize (self.size.height (), self.size.width ())

            self.zoom


    def release(self):
        """Stop referencing the QPixmap object so its memory is released."""
        self.pixmap = None


class Filter (QWidget):
    label_map= { 'K': 'Keep', 'T': 'Take', 'S': 'Stitch', 'M': 'Compare',
                 'C': 'Crop', 'D': 'Delete', None: '' }

    def __init__ (self, parent, config, new_files):
        QWidget.__init__ (self, parent)
        self.zoomLevel = 1.0
        self.rotation = 0

        self.images = []
        self.src= config['Directories']['mid']
        self.dst= os.getcwd ()
        self.scan (self.src)
        self.new_files = new_files
        self.index= 0
        self.image= None

        self.image_actions= defaultdict (lambda: None)
        self.image_positions= {}
        self.original_position= None

        self.buildUI (parent)

        self.dir_dialog= QFileDialog (self)
        self.dir_dialog.setFileMode (QFileDialog.Directory)


    def buildUI(self, parent):
        # left labels
        self.splitter = QSplitter(self)
        self.splitter.setContentsMargins (QMargins (0, 0, 0, 0))
        self.splitter.setOrientation(Qt.Horizontal)
        self.widget = QWidget(self.splitter)
        self.label_layout = QVBoxLayout(self.widget)

        for count, name in enumerate([ 'exposure_time', 'fnumber', 'iso_speed',
                                    'focal_length', 'date', ]):
            key_label = QLabel(name.replace('_', ' ').title(), self.widget)
            # setattr(self, "key_label_%02d" % count, key_label)
            self.label_layout.addWidget(key_label)

            value_label = QLabel(self.widget)
            value_label.setAlignment(Qt.AlignRight)
            setattr(self, name, value_label)
            self.label_layout.addWidget(value_label)

        # TODO
        s = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.label_layout.addItem(s)

        # main view
        self.scene= QGraphicsScene ()

        self.item= QGraphicsPixmapItem ()
        self.scene.addItem (self.item)

        self.view= QGraphicsView (self.scene, parent)
        self.view.setFrameShadow (QFrame.Plain)
        self.view.setFrameStyle (QFrame.NoFrame)
        self.view.setDragMode (QGraphicsView.ScrollHandDrag)
        self.view.setHorizontalScrollBarPolicy (Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy   (Qt.ScrollBarAlwaysOff)

        brush = QBrush(QColor(20, 20, 20))
        brush.setStyle(Qt.SolidPattern)
        self.view.setBackgroundBrush(brush)

        self.view.show()

        # "status bar"
        self.fname= QLabel (self)
        spacer= QSpacerItem (40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.tag_view= QLabel (self)

        status_bar= QHBoxLayout ()
        status_bar.addWidget (self.fname)
        status_bar.addItem (spacer)
        status_bar.addWidget (self.tag_view)

        w = QWidget(self.splitter)

        v= QVBoxLayout (w)
        v.setContentsMargins (QMargins (0, 0, 0, 0))
        v.addWidget (self.view)
        v.addLayout (status_bar)

        # TODO
        self.splitter.setSizes([10, 90])

        h = QHBoxLayout(self)
        h.setContentsMargins (QMargins (0, 0, 0, 0))
        h.addWidget(self.splitter)

        # now... ACTION!(s)
        for key, slot in ((Qt.Key_Home, self.first_image),
                          (Qt.Key_PageUp, self.prev_ten),
                          (Qt.Key_Backspace, self.prev_image),
                          (Qt.Key_Space, self.next_image),
                          (Qt.Key_PageDown, self.next_ten),
                          (Qt.Key_End, self.last_image),

                          (Qt.Key_F, self.toggle_fullsize),

                          (Qt.Key_K, self.keep),
                          (Qt.Key_T, self.tag),
                          (Qt.Key_S, self.stitch),
                          (Qt.Key_M, self.compare),
                          (Qt.Key_C, self.crop),
                          (Qt.Key_D, self.delete),
                          (Qt.Key_U, self.untag),
                          (Qt.Key_X, self.expunge),
                          (Qt.Key_Return, self.apply),

                          (Qt.CTRL+Qt.Key_O, self.new_dst),
                          (Qt.CTRL+Qt.Key_S, self.save),):
            action= QAction (parent)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect (slot)
            self.view.addAction (action)


    def scan (self, src):
        logger.debug ('scanning %r', src)
        for r, dirs, files in os.walk (os.path.abspath (src)):
            for name in sorted(files):
                if name[-4:].lower () in ('.jpg', '.png'):
                    # logger.info ('found %s' % name)
                    self.images.append(Image(os.path.join(r, name)))


    def rotate_view (self):
        # we have to 'undo' the rotations, so the numbers are negative
        rotate = -self.image.rotation

        # undo the last rotation and apply the new one
        self.view.rotate (-self.rotation+rotate)
        self.rotation= rotate
        logger.debug(rotate, self.rotation)


    def zoom_to_fit(self):
        winSize = self.view.size()
        logger.debug(self.image.size, winSize)

        hZoom = winSize.width()/self.image.size.width()
        vZoom = winSize.height()/self.image.size.height()
        zoomLevel= min (hZoom, vZoom)

        self.zoom (zoomLevel)


    def zoom (self, zoomLevel):
        # logger.info (zoomLevel)
        scale= zoomLevel/self.zoomLevel
        # logger.info ("scaling", scale)
        self.view.scale (scale, scale)

        self.zoomLevel= zoomLevel


    def move_index(self, to=None, how_much=0):
        self.save_position()
        if to is not None:
            self.index = to
        self.index += how_much
        self.index %= len(self.images)
        if self.image is not None:
            self.image.release()
        self.image = self.images[self.index]
        self.image.read()


    def view_position (self):
        view_size= self.view.size ()
        center= QPoint (view_size.width ()/2, view_size.height ()/2)
        position= self.view.mapToScene (center)
        return position


    def show_image (self):
        logger.info (self.image.path)

        self.rotate_view()
        self.item.setPixmap(self.image.pixmap)
        if self.zoomLevel != 1.0:
            self.zoom_to_fit()

        # we might have rotated the view, but the scene still has the image
        # in its original size, so we use that as bounding rect
        boundingRect= QRectF (self.item.pixmap ().rect ())
        logger.debug (boundingRect)
        self.scene.setSceneRect (boundingRect)

        if self.index in self.image_positions:
            self.original_position= None
            position= self.image_positions[self.index]
            logger.debug ("previously moved, back to that point: %f x %f", position.x(), position.y())
            self.view.centerOn (position)
        else:
            # TODO: 'undo' the move
            position= self.view_position ()
            logger.debug ("original position: %f x %f", position.x(), position.y())
            self.original_position= position
            self.view.centerOn (self.item)

        self.update_view()


    def update_view(self):
        self.fname.setText (self.image.path)
        label= self.label_map[self.image_actions[self.image]]
        self.tag_view.setText (label)

        meta = self.image.metadata
        self.date.setText(meta.get_date_time().isoformat())
        self.fnumber.setText(str(meta.get_fnumber()))
        self.focal_length.setText(str(meta.get_focal_length()))
        self.iso_speed.setText(str(meta.get_iso_speed()))

        f = meta.get_exposure_time()
        if f.denominator == 1:
            s= '%ds' % f.numerator
        else:
            s= '%d/%ds' % (f.numerator, f.denominator)
        self.exposure_time.setText(s)


    def save_position (self):
        position= self.view_position ()
        if (   self.original_position is None
            or position.x()!=self.original_position.x()
            or position.y()!=self.original_position.y()):

            logger.debug ("saving position: %f x %f", position.x(), position.y())
            # this way (I hope) I only remember those positions which changed
            self.image_positions[self.index]= position


    # movements
    def first_image (self, *args):
        self.move_index (to=0)
        self.show_image ()

    def prev_ten (self, *args):
        self.move_index (how_much=-10)
        self.show_image ()

    def prev_image (self, *args):
        self.move_index (how_much=-1)
        self.show_image ()

    def next_image (self, *args):
        self.move_index (how_much=+1)
        self.show_image ()

    def next_ten (self, *args):
        self.move_index (how_much=+10)
        self.show_image ()

    def last_image (self, *args):
        self.move_index (to=len (self.images)-1)
        self.show_image ()


    def toggle_fullsize (self, *args):
        # noooooooooooooooothing compares...
        if abs (self.zoomLevel-1.0) < 0.000001:
            # logger.info ('fit')
            self.zoom_to_fit ()
        else:
            # logger.info ('orig')
            self.zoom (1.0)


    # image actions
    # Keep -> /gallery/foo, resized
    def keep (self, *args):
        self.image_actions[self.image]= 'K'
        self.next_image ()

    # Tag -> /gallery/foo, as-is
    def tag (self, *args):
        self.image_actions[self.image]= 'T'
        self.next_image ()

    # Stitch -> 02-new/stitch
    def stitch (self, *args):
        self.image_actions[self.image]= 'S'
        self.next_image ()

    # coMpare -> 03-cur
    def compare (self, *args):
        self.image_actions[self.image]= 'M'
        self.next_image ()

    # Crop -> launch gwenview
    def crop (self, *args):
        self.image_actions[self.image]= 'C'
        self.next_image ()

    # Delete -> /dev/null
    def delete (self, *args):
        self.image_actions[self.image]= 'D'
        self.next_image ()

    def untag (self, *args):
        del self.image_actions[self.image]
        # don't move, most probably I'm reconsidering what to do
        # but change the label
        self.tag_view.setText ('')


    def resize (self, src, dst):
        src_meta= GExiv2.Metadata (src)
        src_p= QPixmap (src)
        dst_p= src_p.scaled (4500, 3000, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)

        dst_p.save (src)
        shutil.move (src, dst)

        # copy all the metadata
        dst_meta= GExiv2.Metadata (dst)
        for tag in src_meta.get_tags ():
            dst_meta[tag]= src_meta[tag]
        dst_meta.save_file ()


    def apply (self, *args):
        hugin= False

        if len ([ action for action in self.image_actions.values ()
                         if action in ('K', 'T')])>0:
            self.new_dst ()

        for img, action in sorted (self.image_actions.items (),
                                   key=lambda s: s[0].path):  # sort by fname
            src = img.path
            dst= os.path.join (self.dst, os.path.basename (src))

            try:
                if src in self.new_files and action not in ('C', 'D'):
                    # rename
                    src= rename_file (src)

                if   action=='K':
                    # Keep -> /gallery/foo, as-is
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)

                elif action=='T':
                    # Tag -> /gallery/foo, resized
                    self.resize (src, dst)

                elif action=='S':
                    # Stitch -> 02-new/stitch
                    dst= os.path.join ('/home/mdione/Pictures/incoming/02-new/stitch',
                                    os.path.basename (src))
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)
                    hugin= True

                elif action=='M':
                    # coMpare -> 03-cur
                    dst= os.path.join ('/home/mdione/Pictures/incoming/03-cur',
                                    os.path.basename (src))
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)

                    new_root= '/home/mdione/Pictures/incoming/03-cur'
                    old_root= self.src

                elif action=='C':
                    # Crop -> launch gwenview
                    os.system ('gwenview %s' % src)

                    # asume the file was saved under a new name
                    # logger.info ("%s -> %s" % (src, dst))
                    # shutil.move (src, dst)


                elif action=='D':
                    # Delete -> /dev/null
                    os.unlink (src)
                    logger.info ("%s deleted" % (src, ))
            except FileNotFoundError as e:
                logger.info (e)

        if hugin:
            os.system ('hugin')

        self.reset ()


    def expunge (self, *args):
        for img, action in self.image_actions.items ():
            src = img.path
            try:
                if action=='D':
                    # Delete -> /dev/null
                    os.unlink (src)
                    logger.info ("%s deleted" % (src, ))
            except FileNotFoundError as e:
                logger.info (e)

        self.reset ()


    def reset (self, new_root=None):
        if new_root is not None:
            self.src= new_root

        self.image_actions.clear ()
        self.images= []
        self.scan (self.src)


    def new_dst (self, *args):
        self.dir_dialog.setDirectory (self.dst)
        if self.dir_dialog.exec ():
            self.dst= self.dir_dialog.selectedFiles()[0]


    def save (self, *args):
        src= self.image.path
        self.dir_dialog.setDirectory (self.dst)
        if self.dir_dialog.exec ():
            dst_dir= self.dir_dialog.selectedFiles()[0]
            if src in self.new_files:
                src= rename_file (src)

            dst= os.path.join (dst_dir, os.path.basename (src))

            logger.info ("%s -> %s" % (src, dst))
            self.resize (src, dst)

            self.next_image ()


if __name__=='__main__':
    config= ConfigParser ()
    config.read ('omia.ini')

    app= QApplication (sys.argv)

    # import
    src= config['Directories']['src']
    mid= config['Directories']['mid']
    new= workflow.import_files (src, mid)

    win= QMainWindow ()

    view= Filter (win, config, new)
    firstImage= QTimer.singleShot (200, view.first_image)

    win.setCentralWidget (view)
    win.showFullScreen ()

    app.exec_ ()
