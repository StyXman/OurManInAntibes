#! /usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2016 Marcos Dione <mdione@grulic.org.ar>

import os
import os.path
import sys
from collections import defaultdict
import shutil

from PyQt4.QtGui import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt4.QtGui import QPixmap, QGraphicsPixmapItem, QAction, QKeySequence
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLabel, QSpacerItem, QSizePolicy
from PyQt4.QtGui import QFrame, QBrush, QColor, QWidget
from PyQt4.QtCore import QTimer, QSize, Qt, QRectF, QMargins

from gi.repository import GExiv2, GLib

# TODO: original size + navigation
# TODO: config file
class Filter (QWidget):
    def __init__ (self, parent, src, dst):
        QWidget.__init__ (self, parent)
        self.zoomLevel= 1.0
        self.rotation= 0

        self.src= src
        self.dst= dst
        self.files= []
        self.image_actions= defaultdict (lambda: None)
        self.scan (src)
        self.index= 0

        self.buildUI (parent)


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

                          (Qt.Key_K, self.keep),
                          (Qt.Key_T, self.tag),
                          (Qt.Key_S, self.stitch),
                          (Qt.Key_C, self.compare),
                          (Qt.Key_P, self.crop),
                          (Qt.Key_D, self.delete),
                          (Qt.Key_U, self.untag),
                          (Qt.Key_Return, self.apply)):
            action= QAction (parent)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect (slot)
            self.view.addAction (action)


    def scan (self, src):
        # print ('scanning %s' % src)
        for r, dirs, files in os.walk (os.path.abspath (src)):
            for name in sorted(files):
                if name[-4:].lower () in ('.jpg', '.png'):
                    # print ('found %s' % name)
                    self.files.append (os.path.join (r, name))


    def rotate (self, metadata, origImgSize):
        # Qt only handles orientation properly from v5.5
        try:
            # try directly to get the tag, because sometimes get_tags() returns
            # tags that don't actually are in the file
            rot= metadata['Exif.Image.Orientation']
        except KeyError:
            # guess :-/
            print ("rotation 'guessed'")
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
        # print (rot, rotate, self.rotation)

        return imgSize


    def zoomFit (self, imgSize):
        winSize= self.view.size ()
        # print (imgSize, winSize)

        # we might have rotated the view, but the scene still has the image
        # in its original size, so we use that as bounding rect
        boundingRect= QRectF (self.item.pixmap ().rect ())
        self.scene.setSceneRect (boundingRect)

        hZoom= winSize.width  ()/imgSize.width  ()
        vZoom= winSize.height ()/imgSize.height ()
        zoomLevel= min (hZoom, vZoom)
        # print (zoomLevel)

        scale= zoomLevel/self.zoomLevel
        # print ("scaling", scale)
        self.view.scale (scale, scale)
        self.view.centerOn (self.item)
        self.zoomLevel= zoomLevel


    def move_index(self, inc):
        self.index+= inc
        self.index%= len (self.files)

        return self.files[self.index]


    def show_image (self, fname):
        metadata= GExiv2.Metadata (fname)

        img= QPixmap (fname)
        imgSize= self.rotate (metadata, img.size ())

        self.item.setPixmap (img)
        self.zoomFit (imgSize)

        self.fname.setText (fname)
        self.tag_view.setText (self.image_actions[self.index])


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
        # print (self.image_actions)


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

    # Compare -> 03-cur
    def compare (self, *args):
        self.image_actions[self.index]= 'C'
        self.next_image ()

    # croP -> 03-cur too
    def crop (self, *args):
        self.image_actions[self.index]= 'P'
        self.next_image ()

    # Delete -> /dev/null
    def delete (self, *args):
        self.image_actions[self.index]= 'D'
        self.next_image ()

    def untag (self, *args):
        del self.image_actions[self.index]
        self.next_image ()


    def apply (self, *args):
        hugin= False
        gwenview= False

        for index, action in self.image_actions.items ():
            src= self.files[index]
            if   action=='K':
                pass

            elif action=='T':
                dst= os.path.join (self.dst, os.path.basename (src))
                print ("%s -> %s" % (src, dst))
                shutil.move (src, dst)

            elif action=='S':
                dst= os.path.join ('/home/mdione/Pictures/incoming/02-new/stitch',
                                   os.path.basename (src))
                print ("%s -> %s" % (src, dst))
                shutil.move (src, dst)
                hugin= True

            elif action in ('C', 'P'):
                dst= os.path.join ('/home/mdione/Pictures/incoming/03-cur',
                                   os.path.basename (src))
                print ("%s -> %s" % (src, dst))
                shutil.move (src, dst)
                gwenview= '/home/mdione/Pictures/incoming/03-new'

            elif action=='P':
                dst= os.path.join ('/home/mdione/Pictures/incoming/02-new/crop',
                                   os.path.basename (src))
                print ("%s -> %s" % (src, dst))
                shutil.move (src, dst)
                gwenview= '/home/mdione/Pictures/incoming/02-crop'

            elif action=='D':
                os.unlink (src)
                print ("%s deleted" % (src, ))

        self.image_actions.clear ()
        self.scan (self.src)


if __name__=='__main__':
    if len (sys.argv)<3:  # awwww :)
        print ("""usage: %s SRC DST

SRC points to the root directory where the images are going to be picked up.
DST points to the directory where the images are going to be put.
""" % sys.argv[0])
        sys.exit (1)

    app= QApplication (sys.argv)
    win= QMainWindow ()

    view= Filter (win, sys.argv[1], sys.argv[2])
    firstImage= QTimer.singleShot (200, view.first_image)

    win.setCentralWidget (view)
    win.showFullScreen ()

    app.exec_ ()
