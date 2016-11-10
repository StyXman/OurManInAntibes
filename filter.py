#! /usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2016 Marcos Dione <mdione@grulic.org.ar>

import os
import os.path
import sys
from collections import defaultdict
import shutil
from configparser import ConfigParser

from PyQt4.QtGui import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt4.QtGui import QPixmap, QGraphicsPixmapItem, QAction, QKeySequence
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt4.QtGui import QFrame, QBrush, QColor, QWidget, QFileDialog
from PyQt4.QtCore import QTimer, QSize, Qt, QRectF, QMargins

import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2, GLib

# TODO: original size + navigation
# TODO: config file

import logging
log_format= "%(asctime)s %(name)16s:%(lineno)-4d (%(funcName)-21s) %(levelname)-8s %(message)s"
logging.basicConfig (level=logging.DEBUG, format=log_format)
logger= logging.getLogger ("omia")

class Filter (QWidget):
    label_map= { 'K': 'Keep', 'T': 'Tag', 'S': 'Stitch', 'M': 'Compare',
                 'C': 'Crop', 'D': 'Delete', None: '' }

    def __init__ (self, parent, config):
        QWidget.__init__ (self, parent)
        self.zoomLevel= 1.0
        self.rotation= 0

        self.img= None
        self.metadata= None

        self.files= []
        self.image_actions= defaultdict (lambda: None)

        self.src= config['Directories']['mid']
        self.dst= None
        self.scan (self.src)
        self.index= 0

        self.buildUI (parent)

        self.dir_dialog= QFileDialog (self)
        self.dir_dialog.setFileMode (QFileDialog.Directory)


    def buildUI(self, parent):
        self.scene= QGraphicsScene ()

        self.item= QGraphicsPixmapItem ()
        self.scene.addItem (self.item)

        self.view= QGraphicsView (self.scene, parent)
        self.view.setFrameShadow (QFrame.Plain)
        self.view.setFrameStyle (QFrame.NoFrame)

        brush = QBrush(QColor(0, 0, 0))
        brush.setStyle(Qt.SolidPattern)
        self.view.setBackgroundBrush(brush)

        self.view.show()

        self.fname= QLabel (self)
        spacer= QSpacerItem (40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.tag_view= QLabel (self)

        h= QHBoxLayout ()
        h.addWidget (self.fname)
        h.addItem (spacer)
        h.addWidget (self.tag_view)

        v= QVBoxLayout (self)
        v.setContentsMargins (QMargins (0, 0, 0, 0))
        v.addWidget (self.view)
        v.addLayout (h)

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
                    self.files.append (os.path.join (r, name))


    def rotate (self):
        origImgSize= self.img.size ()
        # Qt only handles orientation properly from v5.5
        try:
            # try directly to get the tag, because sometimes get_tags() returns
            # tags that don't actually are in the file
            rot= self.metadata['Exif.Image.Orientation']
        except KeyError:
            # guess :-/
            logger.info ("rotation 'guessed'")
            rot= '1'

        # see http://www.daveperrett.com/images/articles/2012-07-28-exif-orientation-handling-is-a-ghetto/EXIF_Orientations.jpg
        # we have to 'undo' the rotations, so the numbers are negative
        if rot=='1':
            rotate= 0
            imgSize= origImgSize
        if rot=='8':
            rotate= -90
            imgSize= QSize (origImgSize.height (), origImgSize.width ())
        if rot=='3':
            rotate= -180
            imgSize= origImgSize
        if rot=='6':
            rotate= -270
            imgSize= QSize (origImgSize.height (), origImgSize.width ())

        # undo the last rotation and apply the new one
        self.view.rotate (-self.rotation+rotate)
        self.rotation= rotate
        # logger.info (rot, rotate, self.rotation)

        return imgSize


    def zoom_to_fit (self):
        winSize= self.view.size ()
        # logger.info (imgSize, winSize)

        # we might have rotated the view, but the scene still has the image
        # in its original size, so we use that as bounding rect
        boundingRect= QRectF (self.item.pixmap ().rect ())
        logger.info (boundingRect)
        self.scene.setSceneRect (boundingRect)

        hZoom= winSize.width  ()/self.imgSize.width  ()
        vZoom= winSize.height ()/self.imgSize.height ()
        zoomLevel= min (hZoom, vZoom)

        self.zoom (zoomLevel)


    def zoom (self, zoomLevel):
        # logger.info (zoomLevel)
        scale= zoomLevel/self.zoomLevel
        # logger.info ("scaling", scale)
        self.view.scale (scale, scale)
        self.view.centerOn (self.item)

        self.zoomLevel= zoomLevel


    def move_index(self, inc):
        self.index+= inc
        self.index%= len (self.files)

        return self.files[self.index]


    def show_image (self, fname):
        self.metadata= GExiv2.Metadata (fname)

        self.img= QPixmap (fname)
        self.imgSize= self.rotate ()

        self.item.setPixmap (self.img)
        if self.zoomLevel!=1.0:
            self.zoom_to_fit ()

        self.fname.setText (fname)
        label= self.label_map[self.image_actions[self.index]]
        self.tag_view.setText (label)


    # movements
    def first_image (self, *args):
        self.index= 0
        self.show_image (self.files[self.index])

    def prev_ten (self, *args):
        fname= self.move_index (-10)
        self.show_image (fname)

    def prev_image (self, *args):
        fname= self.move_index (-1)
        self.show_image (fname)

    def next_image (self, *args):
        fname= self.move_index (+1)
        self.show_image (fname)

    def next_ten (self, *args):
        fname= self.move_index (+10)
        self.show_image (fname)

    def last_image (self, *args):
        self.index= len (self.files)-1
        self.show_image (self.files[self.index])
        # logger.info (self.image_actions)


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
        self.image_actions[self.index]= 'K'
        self.next_image ()

    # Tag -> /gallery/foo, as-is
    def tag (self, *args):
        self.image_actions[self.index]= 'T'
        self.next_image ()

    # Stitch -> 02-new/stitch
    def stitch (self, *args):
        self.image_actions[self.index]= 'S'
        self.next_image ()

    # coMpare -> 03-cur
    def compare (self, *args):
        self.image_actions[self.index]= 'M'
        self.next_image ()

    # Crop -> launch gwenview
    def crop (self, *args):
        self.image_actions[self.index]= 'C'
        self.next_image ()

    # Delete -> /dev/null
    def delete (self, *args):
        self.image_actions[self.index]= 'D'
        self.next_image ()

    def untag (self, *args):
        del self.image_actions[self.index]
        # don't move, most probably I'm reconsidering what to do
        # but change the label
        self.tag_view.setText ('')


    def apply (self, *args):
        hugin= False
        gwenview= False

        for index, action in self.image_actions.items ():
            src= self.files[index]
            dst= os.path.join (self.dst, os.path.basename (src))

            try:
                if   action=='K':
                    # Keep -> /gallery/foo, resized
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)

                elif action=='T':
                    src_meta= GExiv2.Metadata (src)
                    src_p= QPixmap (src)
                    dst_p= src_p.scaled (4500, 3000, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation)

                    dst_p.save (dst)

                    # copy all the metadata
                    dst_meta= GExiv2.Metadata (dst)
                    for tag in src_meta.get_tags ():
                        dst_meta[tag]= src_meta[tag]
                    dst_meta.save_file ()

                    # os.unlink (src)

                elif action=='S':
                    dst= os.path.join ('/home/mdione/Pictures/incoming/02-new/stitch',
                                    os.path.basename (src))
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)
                    hugin= True

                elif action=='M':
                    dst= os.path.join ('/home/mdione/Pictures/incoming/03-cur',
                                    os.path.basename (src))
                    logger.info ("%s -> %s" % (src, dst))
                    shutil.move (src, dst)

                    new_root= '/home/mdione/Pictures/incoming/03-cur'
                    old_root= self.src

                elif action=='C':
                    os.system ('gwenview %s' % src)

                    # asume the file was saved under a new name
                    # logger.info ("%s -> %s" % (src, dst))
                    # shutil.move (src, dst)


                elif action=='D':
                    os.unlink (src)
                    logger.info ("%s deleted" % (src, ))
            except FileNotFoundError as e:
                logger.info (e)

        if hugin:
            os.system ('hugin')

        self.reset (new_root)


    def reset (self, new_root=None):
        if new_root is not None:
            self.src= new_root

        self.image_actions.clear ()
        self.scan (self.src)


    def new_dst (self, *args):
        self.dir_dialog.setDirectory (self.dst)
        if self.dir_dialog.exec ():
            self.dst= self.dir_dialog.selectedFiles()[0]


    def save (self, *args):
        src= self.files[self.index]
        self.dir_dialog.setDirectory (self.dst)
        if self.dir_dialog.exec ():
            dst_dir= self.dir_dialog.selectedFiles()[0]
            dst= os.path.join (dst_dir, os.path.basename (src))

            logger.info ("%s -> %s" % (src, dst))
            shutil.move (src, dst)

            self.next_image ()


if __name__=='__main__':
    config= ConfigParser ()
    config.read ('omia.ini')


    app= QApplication (sys.argv)
    win= QMainWindow ()

    view= Filter (win, config)
    firstImage= QTimer.singleShot (200, view.first_image)

    win.setCentralWidget (view)
    win.showFullScreen ()

    app.exec_ ()
