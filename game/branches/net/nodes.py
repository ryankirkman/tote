"""
This module defines several the Node class and several subclasses that are used
as Ogre (3d-world) representations of game-world objects (such as players or
static map objects like trees and rocks, generally represented by a mesh).
These classes uses the adapter pattern to implement Ogre's SceneNode
functionality. This class is responsible for things such as mapping game-world
coordinates to 3d-world coordinates and displaying animations.

These classes listen to events fired by their game-world object counterparts to
perform actions (such as starting an animation) and make updates (such as
moving the mesh in the 3d-world to objcet the player moving in the game-world).

*NOTE: The following is strongly recommended as best use of these classes:
 - The interaction between the game state and these classes should be one way
   (from the game state to these classes). Do not directly interact with the
   game state (e.g., the node's game state counterpart) in any way.
 - Any information needed about the game state should be obtained via event
   handler parameters and the game state should not be directly referenced.
"""

from __future__ import division
import math
import gamestate.abilities

class Node(object):
    _unique_count = 0
    @staticmethod
    def _unique(prefix=""):
        """ Return a unique name prefixed with the optional parameter. """
        Node._unique_count += 1
        return "%s%s" % (prefix, Node._unique_count)
    
    def __init__(self, sceneManager, gameObject):
        # Create a SceneNode for this Node (attached to RootSceneNode).
        self.sceneManager = sceneManager
        self.sceneNode = sceneManager.getRootSceneNode().createChildSceneNode()
        
        # Create an Entity (to represent this Node with a 3D mesh) and attach
        # it to the SceneNode. The Entity is configured with a default rotation
        # offset and scale.
        self.entity = sceneManager.createEntity(Node._unique("EntityNinja"), "ninja.mesh")
        entityNode = self.sceneNode.createChildSceneNode()
        entityNode.attachObject(self.entity)
        entityNode.setScale(.1, .1, .1)
        entityNode.rotate((0, -1, 0), math.pi/2)
        
        # Create a dict of our available animations. The animations are stored
        # as a tuple of the animation state and the speed at which the
        # animation should be played.
        self.animations = { }
        self.animations["idle"] = (self.entity.getAnimationState("Idle2"), 1)
        self.animations["run"] = (self.entity.getAnimationState("Walk"), 3)
        self.animations["ability_1"] = (self.entity.getAnimationState("Attack3"), 1)
        
        # Like animations, create a dict of our available particle effects.
        # The particle effects are stored a tuple of the ParticleSystem and the
        # SceneNode that the ParticleSystem is attached to.
        self.particle_effects = { }
        self._particle_effect_init("FireTrail", position=(0, 1, 0))
        
        # Start the idle animation
        self.animation_start("idle")
        
        # Initialize the position and rotation to the GameObject's current values.
        self.rotation = 0
        self.sceneNode.position = (gameObject.position[0], 0, gameObject.position[1])
        self.on_rotation_changed(gameObject, gameObject.rotation)
        
        # Listen to the events we care about.
        gameObject.rotation_changed += self.on_rotation_changed
        
    ## Animations
    def animation_start(self, name):
        """ Play and loop the animation with the given name. """
        anim, speed = self.animations[name]
        anim.setLoop(True)
        anim.setEnabled(True)
        
    def animation_playonce(self, name, weight=1):
        """ Play the animation witht he given name once and then stop. """
        anim, speed = self.animations[name]
        anim.setLoop(False)
        anim.setEnabled(True)
        anim.setWeight(weight)
        anim.setTimePosition(0)
        
    def animation_stop(self, name):
        """ Stop the animation with the given name. """
        anim, speed = self.animations[name]
        anim.setEnabled(False)
        
    def animations_stopall(self):
        """ Stop all animations. """
        for name in self.animations:
            anim, speed = self.animations[name]
            anim.setEnabled(False)
        
    def animations_addtime(self, time):
        """ Add time to all enabled animations. """
        for name in self.animations:
            anim, speed = self.animations[name]
            if anim.getEnabled():
                anim.addTime(time*speed)
                if anim.hasEnded():
                    anim.setEnabled(False)
    
    ## Particle Effects
    def _particle_effect_init(self, name, position=(0,0,0), rotation=0, systemname=None):
        """
        Initialize the particle effect with the given parameters.
        Parameters:
        name - The name for this particle effect.
        position - The position of the SceneNode the ParticleSystem is attached to.
        rotation - The rotation of the SceneNode the ParticleSystem is attached to.
        systemname - The name of the particle_system to use, defaults to the
            name of the particle effect.
        """
        systemname = systemname or name
        system = self.sceneManager.createParticleSystem(Node._unique("PE%s" % name), systemname)
        node = self.sceneNode.createChildSceneNode()
        node.attachObject(system)
        node.position = position
        node.rotate((0, -1, 0), rotation)
        self.particle_effects[name] = (system, node)
        self.particle_effect_stop(name)

    def particle_effect_start(self, name):
        """ Enable the particle effect with the given name. """
        (system, node) = self.particle_effects[name]
        for i in xrange(system.getNumEmitters()):
            system.getEmitter(i).setEnabled(True)
            
    def particle_effect_stop(self, name):
        """ Disable the particle effect with the given name. """
        (system, node) = self.particle_effects[name]
        for i in xrange(system.getNumEmitters()):
            system.getEmitter(i).setEnabled(False)
    
    ## Game state event listeners
    def on_rotation_changed(self, gameObject, rotation):
        delta = rotation - self.rotation
        self.sceneNode.rotate((0, -1, 0), delta)
        self.rotation = rotation


class MobileNode(Node):
    def __init__(self, sceneManager, mobileObject):
        Node.__init__(self, sceneManager, mobileObject)
        
        # Listen to the events we care about.
        mobileObject.position_changed += self.on_position_changed

    ## Game state event listeners
    def on_position_changed(self, mobileObject, position):
        self.sceneNode.position = (position[0], 0, position[1])


class PlayerNode(MobileNode):
    def __init__(self, sceneManager, player):
        MobileNode.__init__(self, sceneManager, player)
        
        # Listen to the events we care about.
        player.is_moving_changed += self.on_is_moving_changed
        player.is_charging_changed += self.on_is_charging_changed
        player.ability_used += self.on_ability_used
        
    def on_is_moving_changed(self, gameObject, is_moving):
        # Play running animations when the player 
        if is_moving:
            self.animation_stop("idle")
            self.animation_start("run")
        else:
            self.animation_stop("run")
            self.animation_start("idle")
            
    def on_is_charging_changed(self, player, is_charging):
        # Start/stop the charging particle effect and set the animation speed.
        multi = gamestate.abilities.FireFlameRushInstance.charge_speed_multiplier
        (anim, speed) = self.animations["run"]
        if is_charging:
            self.particle_effect_start("FireTrail")
            self.animations["run"] = (anim, speed * multi)
        else:
            self.particle_effect_stop("FireTrail")
            self.animations["run"] = (anim, speed / multi)
    
    def on_ability_used(self, player, index):
        if player.element.type == "earth":
            if index == 1:
                # Earth : Primary
                # Play the animation with weight 100 so that it basically overrides
                # any other animations currently playing.
                # @todo: use an actual solution instead of weight hack.
                self.animation_playonce("ability_1", 100)

        elif player.element.type == "fire":
            if index == 1:
                # Fire : Primary
                # Play the animation with weight 100 so that it basically overrides
                # any other animations currently playing.
                # @todo: use an actual solution instead of weight hack.
                self.animation_playonce("ability_1", 100)
            elif index == 2:
                # Fire :  Flame Rush
                pass

    
