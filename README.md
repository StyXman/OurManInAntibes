`ananme` - a simple photo workflow

This tool helps me (an possibly others) to sift through photos for selection.

= Features =

* Import images from a directory.
* Graphical, but mostly kerboard driven.
* Can pan in native resolution mode with the mouse by dragging.

= Model =

`ananke` starts by importing images from a src directory into a mid, incoming
or working directory. Then you can move between all the images in the incoming
directory. Each image can be tagged so later different actions are applied to
them. This means that you can safely tag files for deletion and undo the action
without losing any image! The current action list is:

* Delete: if you're a bad or trigger happy photographer, this is probably the
  most importante one.
* Crop: it launches `gwenview` for cropping, because native cropping is not
  implemented yet.
* Take: the photo will be moved to the dst directory, but it will be resized
  first. The target size depends on the original size.
* Keep: like Take, but no resizing.
* Stitch: the image will be put in a stitching directory. Later, `huging` will
  be launched on this directory. We don't plan to implement stitching natively.
* coMpare: the image is added to a compare set.
* Untag: remove any previous tag.

Applying a new tag will overwrite the previous tag. Once you're done tagging,
hit <ENTRE> and `ananke` will apply the commands for each tag.

The interface is very simple: it runs fullscreen; it has a left panel with some
image attributes (more to
come), a main panel with the current image, and a pseudo-status bar with the
image's path and current tag. The view can be toggled between full view or
native resolution. As mentioned, you can pan the image in the latter.

= Shortcuts =

Most keyboard shortcuts are single keys. The commands for the tags are the
uppercase letter in the tag list ('D' for Delete, 'M' for coMpare, etc). Also:

* <HOME>: First image.
* <PgUp>: Jump 10 images backward.
* <BACK>: Previous image.
* <SPACE>: Next image.
* <PgDn>: Jump 10 images forward.
* <END>: Last image.
* F: Toggle between full view and native resolution.
* C-s: Immediately save this image.
* C-m: Enter compare mode. Exit with <ENTER>
* Mouse drag or cursor keys: pan the image in native resolution mode. Very useful
  in compare mode to align images.
* X: Expunge images marked for deletion now. Very dangerous.
* <ENTER>: apply all the commands. A dialog will pop up so you can select the
  dst directory.

= Shortcomings (a.k.a bugs) =

Be patient with me, I think I wrote this program in some 20h...

* Screens starts split in half! Yes, I know, I couldn't find how to fix it yet.
  Expansion policies are confusing. Just drag the handle left until the labels
  give some resistance.
* The labels are spread vertically instead of all in the top! Same problem, but
  no workaround this time, sorry.
* I can't exit fullscreen mode! Nope, you can't.
* I can't recognize if I'm in compare mode or not! Yeap, sorry about that, can't
  think of a UI element to show that. Maybe I should really go for a status
  bar...
* The UI hangs when apllying! Background tasks suck, just let it finish resizing
  your images.
