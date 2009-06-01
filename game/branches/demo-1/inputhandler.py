from __future__ import division

import ogre.io.OIS as OIS
import gui

import math

KEYBOARD_CONTROLS = {
    "ABILITY_2": OIS.KC_2,
    "ABILITY_3": OIS.KC_3,
    "ABILITY_4": OIS.KC_4,
}

MOUSE_CONTROLS = {
    # The player will face towards the mouse cursor while this button is
    # pressed.
    "FACE": OIS.MB_Right,
    
    # The player will move forward while this button is pressed.
    "MOUSEMOVE": OIS.MB_Right,
    "ABILITY_1": OIS.MB_Left,
}

class InputHandler(OIS.MouseListener, OIS.KeyListener):
    """
    This class handles all user device input event handlers with the defined
    callback functions. This class modifies the game state directly with a
    reference to a player object that represents the current playing player.
    This class also has a reference to the scene object to get information from
    and make changes to the camera, window, and viewport.
    
    The *Pressed() and *Released() event handlers should handle state changes
    that occur only on the pressed and released events, whereas process()
    should handle state changes that occur continuously while the key is kept
    pressed down.
    """
    
    def __init__(self, mouse, keyboard, scene, player):
        OIS.MouseListener.__init__(self)
        OIS.KeyListener.__init__(self)
        self.mouse = mouse
        self.keyboard = keyboard
        self.scene = scene
        self.viewport = vp = self.scene.camera.getViewport()
        self.player = player
        
    def capture(self):
        self.mouse.capture()
        self.keyboard.capture()
        self.process()
        
    def process(self):
        # Input states that need to be handled every state are checked
        # here. This is similar to unbufferd input.
        mouseState = self.mouse.getMouseState()
        
        if mouseState.buttonDown(MOUSE_CONTROLS["FACE"]):
            mousex = mouseState.X.abs
            mousey = mouseState.Y.abs
            angle = math.atan2(mousey - self.viewport.actualHeight/2,
                               mousex - self.viewport.actualWidth/2)
            self.player.rotation = angle
            
        self.player.is_moving = mouseState.buttonDown(MOUSE_CONTROLS["MOUSEMOVE"])

    def mouseMoved(self, event):
        return True

    def mousePressed(self, event, id):
        if id == MOUSE_CONTROLS["ABILITY_1"]:
            self.player.use_ability(1)
        
        # Inject mouse press to UI elements.
#        for element in self.scene.gui_elements:
#            if isinstance(element, gui.IClickable):
#                element.inject_mouse_press(id,
#                    event.get_state().X.abs, event.get_state().Y.abs)

        return True

    def mouseReleased(self, event, id):
        # Inject mouse release to UI elements.
#        for element in self.scene.gui_elements:
#            if isinstance(element, gui.IClickable):
#                element.inject_mouse_release(id,
#                    event.get_state().X.abs, event.get_state().Y.abs)

        return True

    def keyPressed(self, event):
        # Quit the application if we hit the escape button
        if event.key == OIS.KC_ESCAPE:
            self.scene.quit = True
        if event.key == KEYBOARD_CONTROLS["ABILITY_2"]:
            self.player.use_ability(2)
        if event.key == KEYBOARD_CONTROLS["ABILITY_3"]:
            self.player.use_ability(3)
        if event.key == KEYBOARD_CONTROLS["ABILITY_4"]:
            self.player.use_ability(4)
        return True

    def keyReleased(self, event):
        return True