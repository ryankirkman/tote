from twisted.internet import reactor, protocol

import threading, time, struct
from Queue import Queue
from event import Event
import packets

class ServerProtocol(protocol.Protocol):
    def connectionMade(self):
        self.factory.client_count += 1
        self.client_id = self.factory.client_count
        self.player = None
        self.factory.clients.append(self)
        print "New connection #%s client=%s from %s." % \
            (len(self.factory.clients), self.client_id, self.transport.getPeer())
        self.factory.client_connected(self)
        self.current_packet = None
        self.buffer = ""

    def connectionLost(self, reason):
        self.factory.clients.remove(self)
        print "Lost connection #%s client=%s from %s." % \
            (len(self.factory.clients), self.client_id, self.transport.getPeer())

    def dataReceived(self, data):
        self.buffer += data
        self._processBuffer()
    
    def _processBuffer(self):
        if self.current_packet is None and len(self.buffer) >= 3:
            self.current_packet = packets.Packet()
            self.current_packet.unpack(self.buffer)
            
        if self.current_packet is not None and len(self.buffer) >= self.current_packet.size:
            packet = packets.unpack(self.buffer)
            self.buffer = self.buffer[packet.size:]
            self.factory.input.put_nowait((self, packet))
            self.current_packet = None
            self._processBuffer()


class GameServer(protocol.ServerFactory):
    protocol = ServerProtocol
    
    def __init__(self, world, port):
        self.world = world
        self.port = port
        self.client_connected = Event()
        self.input = Queue()
        self.output = Queue()
        self.output_broadcast = Queue()
        self.clients = []
        self.client_count = 0

    def startFactory(self):
        print "Server starting and listening on port %s." % self.port
        pass
        
    def stopFactory(self):
        print "Server stopping."
        pass
    
    def send(self):
        while not self.output.empty():
            (client, packet) = self.output.get_nowait()
            client.transport.write(packet.pack())
        while not self.output_broadcast.empty():
            (packet, ignore) = self.output_broadcast.get_nowait()
            packed = packet.pack()
            for client in self.clients:
                if client.player is not None and client.player == ignore:
                    continue
                client.transport.write(packed)
        
    def go(self):
        reactor.listenTCP(self.port, self)
        reactor.run(installSignalHandlers=0)
        
    def stop(self):
        reactor.stop()