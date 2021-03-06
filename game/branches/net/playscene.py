from __future__ import division
import threading, time, math

# Import OGRE-specific (and other UI-Client) external packages and modules.
import ogre.renderer.OGRE as ogre
import ogre.io.OIS as OIS
from twisted.internet import reactor

# Import internal packages and modules modules.
import gamestate, net
from net import packets
import SceneLoader
from inputhandler import InputHandler
import nodes

class PlayScene(ogre.FrameListener, ogre.WindowEventListener):
    """
    This class represents the game's main scene - the play scene. This class
    sets up the initial scene and acts as the main game loop (via
    frameStarted()).
    """

    def __init__(self, sceneManager, address, port):
        # Initialize the various listener classes we are a subclass from
        ogre.FrameListener.__init__(self)
        ogre.WindowEventListener.__init__(self)
        
        self.address = address
        self.port = port
        
        self.renderWindow = ogre.Root.getSingleton().getAutoCreatedWindow()
        self.sceneManager = sceneManager
        self.camera = self.sceneManager.getCamera("PrimaryCamera")
        self.cameraNode = self.sceneManager.getSceneNode("PrimaryCamera")
        
        # Create an empty list of nodes
        self.nodes = []
        
        # Set up the scene.
        self.setupScene()
        
        # Init attributes.
        self.player = None
        self.last_update = None

        # Create the inputManager using the supplied renderWindow
        windowHnd = self.renderWindow.getCustomAttributeInt("WINDOW")
        paramList = [("WINDOW", str(windowHnd)), \
                     ("w32_mouse", "DISCL_FOREGROUND"), \
                     ("w32_mouse", "DISCL_NONEXCLUSIVE"), \
                     ("w32_keyboard", "DISCL_FOREGROUND"), \
                     ("w32_keyboard", "DISCL_NONEXCLUSIVE"),]
                     # @todo: add mac/linux parameters
        self.inputManager = OIS.createPythonInputSystem(paramList)

        # Attempt to get the mouse/keyboard input device objects.
        try:
            self.mouse = self.inputManager.createInputObjectMouse(OIS.OISMouse, True)
            self.keyboard = self.inputManager.createInputObjectKeyboard(OIS.OISKeyboard, True)
        except Exception: # Unable to obtain mouse/keyboard input
            raise

        # Use an InputHandler object to handle the callback functions.
        self.inputHandler = InputHandler(self.mouse, self.keyboard, self)
        self.mouse.setEventCallback(self.inputHandler)
        self.keyboard.setEventCallback(self.inputHandler)

        # Set up initial window size.
        self.windowResized(self.renderWindow)

        # Set this to True when we get an event to exit the application
        self.quit = False

        # Listen for any events directed to the window manager's close button
        ogre.WindowEventUtilities.addWindowEventListener(self.renderWindow, self)

    def __del__ (self ):
        # Clean up OIS 
        self.inputManager.destroyInputObjectKeyboard(self.keyboard)
        self.inputManager.destroyInputObjectMouse(self.mouse)
        OIS.InputManager.destroyInputSystem(self.inputManager)
        self.inputManager = None

        ogre.WindowEventUtilities.removeWindowEventListener(self.renderWindow, self)
        self.windowClosed(self.renderWindow)
        
    def setupScene(self):
        ## Load the level.
        # @todo: Remove .scene dependancy and move to external file (format?).
        
        # Load some data from the .scene file
        sceneLoader = SceneLoader.DotSceneLoader("media/testtilescene.scene", self.sceneManager)
        sceneLoader.parseDotScene()
        
        # Create the world.
        self.world = gamestate.world.World()
        
        # Create the client and set listeners.
        self.client = net.client.GameClient(self.world, self.address, self.port)
        self.client.connected += self.on_client_connected
        
        # Start the netclient and connect.
        self.client_thread = threading.Thread(target=self.client.go)
        self.client_thread.start()
        
        # Attach a handler to world.object_added
        self.world.object_added += self.on_world_object_added
        
        # Set up the TestScene
        self.scene = gamestate.scenes.TestScene(self.world)

        # Setup camera
        self.camera.nearClipDistance = 1
        self.camera.farClipDistance = 500
        self.camera.setProjectionType(ogre.PT_ORTHOGRAPHIC)

        # THIS SPECIFIES THE HEIGHT OF THE ORTHOGRAPHIC WINDOW
        # the width will be recalculated based on the aspect ratio
        # in ortho projection mode, decreasing the size of the window
        # is equivalent to zooming in, increasing is the equivalent of
        # zooming out.
        self.camera.setOrthoWindowHeight(200)

        # Setup camera node
        self.cameraNode.position = (0, 100, 100)
        self.cameraNode.pitch(ogre.Degree(-45))

    def frameStarted(self, event):
        """ 
        Called before a frame is displayed, handles events
        (also those via callback functions, as you need to call capture()
        on the input objects)

        Returning False here exits the application (render loop stops)
        """
        
        dt = event.timeSinceLastFrame
        
        # Get buffered input from server and process it.
        while not self.client.input.empty():
            packet = self.client.input.get_nowait()
            self.process_packet(packet)

        # Capture any buffered events (and fire any callbacks).
        self.inputHandler.capture()
        
        # Update the game state world.
        self.world.update(dt)
        
        # Send an PlayerUpdate packet to the server if appropriate.
        self._send_update()
        
        # Send buffered output to server.
        reactor.callFromThread(self.client.send)
        
        # Add time to animations.
        for node in self.nodes:
            node.animations_addtime(dt)

        # Neatly close our FrameListener if our renderWindow has been shut down
        # or we are quitting.
        if self.renderWindow.isClosed() or self.quit:
            return False
        
        return True
    
    ## Net event callbacks & helpers
    
    def _send_update(self):
        """ Sends a PlayerUpdate packet to the server if appropriate. """
        if self.player is None:
            return

        update = self._get_update()
        if self.last_update is not None:
            update_time, last_update = self.last_update
            
            # Don't send if we've sent in the last 0.1s.
            if update_time + 0.05 > self.world.time:
                return
                
            # Don't send if info hasn't changed since the last update.
            if last_update.x == update.x and last_update.z == update.z and \
                last_update.rotation == update.rotation and \
                last_update.move_speed == update.move_speed and \
                last_update.move_direction == update.move_direction:
                return
        
        print "Sending player update to server."
        self.client.output.put_nowait(update)
        self.last_update = (self.world.time, update)
    
    def _get_update(self):
        """ Returns a PlayerUpdate packet based on the current player state. """
        update = packets.PlayerUpdate()
        update.x, update.z = self.player.position
        update.rotation = self.player.rotation
        if self.player.is_moving:
            update.move_speed = self.player.move_speed
            update.move_direction = self.player.move_direction
        else:
            update.move_speed = 0
            update.move_direction = 0
        return update
        
    
    def process_packet(self, packet):
        ptype = type(packet)
        print "Processing packet=%s: %s from server." % (packet.id, ptype.__name__)
        
        # JoinResponse
        if ptype is packets.JoinResponse:
            # @todo: handle deny
            # Add a player to the world and set it as our active player.
            print "Creating player in world with id=%s." % packet.player_id
            self.player = gamestate.objects.Player(self.world)
            self.world.add_object(self.player, packet.player_id)
            
            # Listen to the player's position change event so we can mvoe the
            # camera with the player.
            self.player.position_changed += self.on_player_position_changed
        
        # ObjectInit
        elif ptype is packets.ObjectInit:
            if packet.object_type == "player":
                object = gamestate.objects.Player(self.world)
            else:
                raise Exception("Invalid object_type")
            # @todo: implement name, owner_id, ttl

            self.world.add_object(object, packet.object_id)
        
        # ObjectUpdate
        elif ptype is packets.ObjectUpdate:
            if not self.world.objects_hash.has_key(packet.object_id):
                return
            object = self.world.objects_hash[packet.object_id]
            print "Updating object id=%s." % object.object_id
            object.rotation = packet.rotation
            try:
                if packet.move_speed > 0:
                    diff_vector = ogre.Vector3(packet.x - object.position[0], 0, packet.z - object.position[1])
                    move_vector = ogre.Vector3(packet.move_speed * math.cos(packet.rotation), 0,
                                               packet.move_speed * math.sin(packet.rotation))
                    resultant = diff_vector + move_vector
                    angle = math.atan2(resultant.z, resultant.x)
                    object.move_speed = packet.move_speed
                    object.rotation = angle
                    object.move_direction = 0
                    object.is_moving = True
                else:
                    object.position = (packet.x, packet.z)
                    object.is_moving = False
            except:
                object.position = (packet.x, packet.z)
    
    def on_client_connected(self):
        packet = packets.JoinRequest()
        # @todo: Get player_name from somewhere.
        packet.player_name = "Player1"
        self.client.output.put_nowait(packet)
        
    ## Game event callbacks
    def on_world_object_added(self, gameObject):
        if gameObject.type == "player":
            self.nodes.append(nodes.PlayerNode(self.sceneManager, gameObject))
        
    def on_player_position_changed(self, mobileObject, position):
        self.cameraNode.position = (position[0], 100, position[1] + 100)

    ## Window event listener callbacks
    def windowResized(self, renderWindow):
        self.mouse.getMouseState().width = renderWindow.width
        self.mouse.getMouseState().height = renderWindow.height
        vp = self.camera.getViewport()
        self.camera.aspectRatio = vp.actualWidth / vp.actualHeight
        # @todo: Scale the image so viewable area remains the same.

    def windowClosed(self, renderWindow):
        # Only close for window that created OIS
        if(renderWindow == self.renderWindow):
            del self