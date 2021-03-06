from __future__ import division

# Import OGRE-specific (and other UI-Client) external packages and modules.
import ogre.renderer.OGRE as ogre
import ogre.gui.CEGUI as CEGUI
from twisted.internet import reactor

# Import other external packages and modules.
import threading, time

# Import internal packages and modules modules.
from playscene import PlayScene
import gamestate, net
from net import packets

class ClientApplication(object):
    app_title = "MyApplication"
    
    def __init__(self, address, port=8981):
        self.address = address
        self.port = port

    def go(self):
        # See Basic Tutorial 6 for details
        self.createRoot()
        self.defineResources()
        self.setupRenderSystem()
        self.createRenderWindow()
        self.initializeResourceGroups()
        self.setupScene()
        self.createFrameListener()
        self.setupCEGUI()
        self.startRenderLoop()
        self.cleanUp()

    def createRoot(self):
        self.root = ogre.Root()

    def defineResources(self):
        # Read the resources.cfg file and add all resource locations in it
        cf = ogre.ConfigFile()
        cf.load("resources.cfg")
        seci = cf.getSectionIterator()
        while seci.hasMoreElements():
            secName = seci.peekNextKey()
            settings = seci.getNext()

            for item in settings:
                typeName = item.key
                archName = item.value
                ogre.ResourceGroupManager.getSingleton().addResourceLocation(archName, typeName, secName)

    def setupRenderSystem(self):
        # Show the config dialog if we don't yet have an ogre.cfg file
        if not self.root.restoreConfig() and not self.root.showConfigDialog():
            raise Exception("User canceled config dialog! (setupRenderSystem)")

    def createRenderWindow(self):
        self.root.initialise(True, self.app_title)
        self.renderWindow = self.root.getAutoCreatedWindow()
        self.renderWindow.setDeactivateOnFocusChange(False)

    def initializeResourceGroups(self):
        ogre.TextureManager.getSingleton().setDefaultNumMipmaps(5)
        ogre.ResourceGroupManager.getSingleton().initialiseAllResourceGroups()

    def setupScene(self):
        self.sceneManager = self.root.createSceneManager(ogre.ST_GENERIC, "PrimarySceneManager")
        
        # Create the camera and attach it to a scene node.
        camera = self.sceneManager.createCamera("PrimaryCamera")
        cameraNode = self.sceneManager.getRootSceneNode().createChildSceneNode('PrimaryCamera')
        cameraNode.attachObject(camera)

        # setup viewport
        vp = self.renderWindow.addViewport(camera)
        vp.backGroundColor = (0, 0, 0)

    def createFrameListener(self):
        self.playScene = PlayScene(self.sceneManager, self.address, self.port)
        self.root.addFrameListener(self.playScene)

    def setupCEGUI(self):
        sceneManager = self.sceneManager

        # CEGUI
        self.renderer = CEGUI.OgreCEGUIRenderer(self.renderWindow, ogre.RENDER_QUEUE_OVERLAY, False, 3000, sceneManager)
        self.system = CEGUI.System(self.renderer)

        # CEGUI.SchemeManager.getSingleton().loadScheme("TaharezLookSkin.scheme")
        # self.system.setDefaultMouseCursor("TaharezLook", "MouseArrow")
        # self.system.setDefaultFont("BlueHighway-12")

        # Uncomment the following to read in a CEGUI sheet (from CELayoutEditor)
        # 
        # self.mainSheet = CEGUI.WindowManager.getSingleton().loadWindowLayout("myapplication.layout")
        # self.system.setGUISheet(self.mainSheet)

    def startRenderLoop(self):
        self.root.startRendering()

    def cleanUp(self):
        # @todo: move this somewhere else
        self.playScene.client.stop()
        pass


class ServerApplication(object):
    def __init__(self, port=8981):
        self.port = port
        
    def go(self):
        self.world = gamestate.world.World()
        self.scene = gamestate.scenes.TestScene(self.world)
        
        self.server = net.server.GameServer(self.world, self.port)
        self.server_thread = threading.Thread(target=self.server.go)
        self.server_thread.start()
        
        self.last_update_time = { }
        
        self.run = True
        
        last = time.clock()
        while self.run:
            new = time.clock()
            dt = new - last
            self.update(dt)
            last = new
    
    def stop(self):
        self.run = False
        self.server.stop()
        
    def update(self, dt):
        # Get buffered input from clients and process it.
        while not self.server.input.empty():
            (client, packet) = self.server.input.get_nowait()
            self.process_packet(client, packet)
        
        # Update the game state world.
        self.world.update(dt)
        
        # Send necessary ObjectUpdate packets.
        for object in self.world.objects:
            # Only send updates for MobileObjects.
            if not isinstance(object, gamestate.objects.MobileObject):
                continue

            if self.last_update_time.has_key(object):
                update_time, updates = self.last_update_time[object]
                
                # Only send if update threshold has expired.
                if update_time + 0.05 > self.world.time:
                    continue
                    
                # Only send if position/rotation/speed/direction has changed.
                last_position = updates[0]
                if object.position == last_position:
                    #print "Skipping id=%s because (%.2f, %.2f) == (%.2f, %.2f)" % \
                    #    (object.object_id, last_position[0], last_position[1], object.position[0], object.position[1])
                    # @todo: implement other attributes than position.
                    continue
            
            print "Broadcasting update for object id=%s." % object.object_id
            update = self._update_from_object(object)
            self.server.output_broadcast.put_nowait((update, object))
            self.last_update_time[object] = (self.world.time, (object.position,))
        
        # Send buffered output to clients.
        reactor.callFromThread(self.server.send)
        
        # Sleep some if we're updating too fast.
        extra = 0.01 - dt
        if extra >= 0.001:
            time.sleep(extra)
    
    def process_packet(self, client, packet):
        ptype = type(packet)
        print "Processing packet=%s: %s from client=%s." % (packet.id, ptype.__name__, client.client_id)
        
        # JoinRequest
        if ptype is packets.JoinRequest:
            # @todo: deny conditions
            # Create the player in the world.
            player = gamestate.objects.Player(self.world)
            player.position = (-20, -20)
            player.rotation = 1.5707963267948966
            self.world.add_object(player)
            client.player = player
            print "Creating player in world with id=%s for client id=%s." % \
                (player.object_id, client.client_id)
                
            # Send the JoinResponse.
            response = packets.JoinResponse()
            response.player_id = player.object_id
            self.server.output.put_nowait((client, response))
            
            # Sent a ObjectInit for the new player obeject to everyone but the player.
            init = packets.ObjectInit()
            init.object_id = player.object_id
            init.object_type = "player"
            self.server.output_broadcast.put_nowait((init, player))
            
            # Send a ObjectUpdate for the new player object to everyone.
            update = self._update_from_object(player)
            self.server.output_broadcast.put_nowait((update, None))
            
            # Send ObjectUpdate and ObjectInit to the player for each object.
            for object in self.world.objects:
                if not isinstance(object, gamestate.objects.MobileObject):
                    continue
                if object == player:
                    continue
                init = packets.ObjectInit()
                init.object_id = object.object_id
                init.object_type = "player"
                self.server.output.put_nowait((client, init))
                update = self._update_from_object(object)
                self.server.output.put_nowait((client, update))
  
        # PlayerUpdate
        elif ptype is packets.PlayerUpdate:
            client.player.position = (packet.x, packet.z)
            client.player.rotation = packet.rotation
            if packet.move_speed > 0:
                client.player.is_moving = True
                client.player.move_speed = packet.move_speed
                client.player.move_direction = packet.move_direction
            else:
                client.player.is_moving = False
    
    def _update_from_object(self, object):
        """ Helper method to create an ObjectUpdate packet from a game object. """
        update = packets.ObjectUpdate()
        update.object_id = object.object_id
        update.x = object.position[0]
        update.z = object.position[1]
        update.rotation = object.rotation
        try:
            if object.is_moving:
                update.move_speed = object.move_speed
                update.move_direction = object.move_direction
            else:
                update.move_speed = 0
                update.move_direction = 0
        except:
            update.move_speed = 0
            update.move_direction = 0
        return update