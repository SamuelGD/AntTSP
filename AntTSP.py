#!/usr/bin/env python
##############################################################################
# Travelling Salesperson Problem          	         Samuel Guilhem-Ducleon  #
##############################################################################
##############################################################################
# EVOLIFE  www.dessalles.fr/Evolife                    Jean-Louis Dessalles  #
#            Telecom ParisTech  2014                       www.dessalles.fr  #
##############################################################################

""" 
	Resolving the Travelling Salesman Problem with ants.
	The ants use pheromone on their way and go from node to node trying to find the shortest trip visiting all nodes.
"""

import sys
from time import sleep
import random
import re
from math import sqrt
		
sys.path.append('..')
sys.path.append('../../..')
import Evolife.Scenarii.Parameters			as EPar
import Evolife.Ecology.Observer				as EO
import Evolife.Ecology.Individual			as EI
import Evolife.Ecology.Group				as EG
import Evolife.Ecology.Population			as EP
import Evolife.QtGraphics.Evolife_Window	as EW
import Evolife.Tools.Tools					as ET

print(ET.boost())	# significantly accelerates python on some platforms


#################################################
# Aspect of ants, food and pheromons on display
#################################################
LinkAspect = ('red', 3)	# 2 = thickness
AntAspect = ('black', 5)	# 4 = size
PheromoneAspect = ('green5', 1)

class Antnet_Observer(EO.Observer):
	""" Stores global variables for observation
	"""
	def __init__(self, Scenario):
		EO.Observer.__init__(self, Scenario)
		self.Positions = []	# stores temporary changes of ant position
		self.Trajectories = []	# stores temporary changes
		# self.recordInfo('CurveNames', [('yellow', 'Year (each ant moves once a year on average)')])
		self.MsgLength = dict()

	def recordChanges(self, Info, Slot='Positions'):
		# stores current changes
		# Info is a couple (InfoName, Position) and Position == (x,y) or a longer tuple
		if Slot ==  'Positions':	self.Positions.append(Info)
		elif Slot == 'Trajectories':	self.Trajectories.append(Info)
		else:	ET.error('Antnet Observer', 'unknown slot')

	def get_info(self, Slot):
		" this is called when display is required "
		if Slot == 'PlotOrders':
			return [(10+M[0], (self.StepId//Gbl.Parameter('PopulationSize'), 
					self.MsgLength[M[1]])) for M in enumerate(self.MsgLength.keys())]	# curves
		elif Slot == 'CurveNames':	
			return [(10+M[0], 'Length of current best path') for M in enumerate(self.MsgLength.keys())]
		elif Slot == 'Trajectories':
			CC = self.Trajectories
			self.Trajectories = []
			return tuple(CC)
		else:	return EO.Observer.get_info(self, Slot)
		
	def get_data(self, Slot):
		if Slot == 'Positions':
			CC = self.Positions
			# print CC
			self.Positions = []
			return tuple(CC)
		else:	return EO.Observer.get_data(self, Slot)

	
class Node:
	"""	Defines a node of the communication network
	"""
	def __init__(self, name, location):
		self.name = name
		self.Size = 5	# for display
		self.Colour = 'blue'	# for display
		
		self.coordinates = location	# physical location

	def draw(self):	return self.name, (self.coordinates + (self.Colour, self.Size))
	
	def highlight(self):	self.Colour = 'red'; self.Size = 8

	def getX(self):
		return self.coordinates[0]

	def getY(self):
		return self.coordinates[1]
	
	def __repr__(self):	return self.name + str(self.coordinates)
	
class Hashmap:
	""" Data structure used to store distances and pheromones whose classes inherit from this one """
	
	def __init__(self, nodes):
		self.values = {}
				
	def getValue(self, node1, node2):
		if (node1, node2) in self.values:
			return self.values[(node1, node2)]
		elif (node2, node1) in self.values:
			return self.values[(node2, node1)]
		elif node1 == node2:
			return 0
		else:
			return -1
			
	def setValue(self, node1, node2, value):
		if (node2, node1) in self.values:
			self.values[(node2, node1)] = value
		else:
			self.values[(node1, node2)] = value
	
class Distances(Hashmap):
	""" Store distances between 2 nodes """
	
	def __init__(self, nodes):
		Hashmap.__init__(self, nodes)
		
		for i in range(0, len(nodes)):
			for j in range(i+1, len(nodes)):
				Hashmap.setValue(self, nodes[i], nodes[j], (nodes[i].getX() - nodes[j].getX())**2 + (nodes[i].getY() - nodes[j].getY())**2)
			
class Pheromones(Hashmap):
	""" Store pheromones between 2 nodes """
	
	def __init__(self, nodes):
		Hashmap.__init__(self, nodes)
		
		for i in range(0, len(nodes)):
			for j in range(i+1, len(nodes)):
				Hashmap.setValue(self, nodes[i], nodes[j], 0)
			
	
class Network:
	""" The network of all nodes which is a graph where all nodes are connected together """

	def __init__(self, Size=100, nbNodes=0):
		#self.TestMessages = []	# Messages used to test the efficiency of the network
		margin = 5 if Size > 20 else 0
		self.nodes = []
		self.currentLength = 0
		
		if Gbl.Parameter('RandomNetwork') and nbNodes > 1:
			self.nodes = [Node('N%d' % i, (random.randint(margin, Size-margin), random.randint(margin, Size-margin))) for i in range(nbNodes)]
		else:	
			# loading network from file
			#	file format:
			#		Name1	x1	y1
			#		Name2	x2	y2
			#		...
			
			try:
				for Line in open(Gbl.Parameter('NetworkFileName'), 'r', 1):	# read one line at a time
					NodeDef = Line.split()
					self.nodes.append(Node(NodeDef[0], tuple(map(int, NodeDef[1:]))))
			except IOError:	ET.error('Unable to find Network description', Gbl.Parameter('NetworkFileName'))
			
			
		self.size = len(self.nodes)
		
		for n in self.nodes:
			print "%s %d %d" % (n.name, n.getX(), n.getY())

		self.distances = Distances(self.nodes)
		self.pheromones = Pheromones(self.nodes)
		
	def nextNode(self, node, visited):
		""" Finds next node from the node in argument """
		
		if len(visited) > self.size: # the length of the trip before the last step cannot be greater than the number of nodes
			ET.error('nextNode', 'Unexpected behavior')
			return None
			
		elif len(visited) == self.size: # the trip ends so we go to the first node
			return visited[0]
			
		else:
			attractions = []
			
			for n in self.nodes:
				if n not in visited:
					if Gbl.Parameter('PheromoneInfluence') > 0:
						pheromoneInfluence = self.pheromones.getValue(node, n) ** Gbl.Parameter('PheromoneInfluence')
					else:
						pheromoneInfluence = 1
					
					if Gbl.Parameter('DistanceInfluence') > 0:
						distanceInfluence = self.distances.getValue(node, n) ** Gbl.Parameter('DistanceInfluence')
					else:
						distanceInfluence = 1
					
					attractions.append((pheromoneInfluence / distanceInfluence, n))
					
			return max(attractions)[1]
			
	def updatePheromones(self, path):
		""" The pheromone increases when an ant ends its tour but also evaporates """

		# Update the pheromones of the path
		length = 0
		for i in range(0, len(path) - 1):
			length += self.distances.getValue(path[i], path[i + 1])
		
		for i in range(0, len(path) - 1):
			pheromone = self.pheromones.getValue(path[i], path[i + 1])
			pheromone += 1./(length**Gbl.Parameter('LengthInfluence'))
			self.pheromones.setValue(path[i], path[i+1], pheromone)
		
		# Evaporating
		
		for i in range(0, len(self.nodes)):
			for j in range(i + 1, len(self.nodes)):
				pheromone = (1 - Gbl.Parameter('EvaporatingCoefficient')) * self.pheromones.getValue(self.nodes[i], self.nodes[j])
				self.pheromones.setValue(self.nodes[i], self.nodes[j], pheromone)
		
			
	def draw(self):
		""" Returns drawing instructions """

		if len(self.nodes):
			node = self.nodes[0]
			
			visited = [node]
			length = 0
			
			while(len(visited) <= self.size):
				node = self.nextNode(node, visited)
				visited.append(node)

				
			for i in range(0, len(visited) - 1):
				length += self.distances.getValue(visited[i], visited[i + 1])
				
			self.currentLength = length
				
			return map(lambda x: ('L%d' % x[0], x[1]), 
				enumerate([visited[i].draw()[1]  + visited[i+1].coordinates + LinkAspect for i in range(0, len(visited) - 1)]))
		else:
			return None
			
	def drawPheromone(self):
		""" Returns drawing instructions for drawing pheromone """
		
		if len(self.nodes):
			instructions = []
			for i in range(0, len(self.nodes)):
				for j in range(i + 1, len(self.nodes)):
					pheromone = self.pheromones.getValue(self.nodes[i], self.nodes[j])
					if pheromone > Gbl.Parameter('PheromoneThreshold'):
						instructions.append(('P%d%d' % (i, j), (self.nodes[i].getX(), self.nodes[i].getY(), 'Black', 0)  + self.nodes[j].coordinates + PheromoneAspect))
				
			return instructions
		else:
			return None

class Ant:
	""" Defines individual agents """
	
	def __init__(self, IdNb, network):
		self.network = network
		self.location = random.choice(network.nodes) # The ant is spawned at a random node
		self.origin = self.location
		self.path = [self.location]
		
		self.ID = IdNb

	def moves(self):
		self.location = self.network.nextNode(self.location, self.path)
		
		self.path.append(self.location)
		self.network.updatePheromones(self.path)
		
		if len(self.path) == (self.network.size + 1): # The ant has been to every node and is back to the first one
			# The ant is reborn
			self.location = random.choice(self.network.nodes)
			self.origin = self.location
			self.path = [self.location]
		
	def draw(self):
		""" Returns drawing instructions """
		return (self.ID, self.location.coordinates + AntAspect)
		
	def __str__(self):
		return "Ant %s at %d %d" % (self.ID, self.location.coordinates[0], self.location.coordinates[1])


class Population:
	""" Defines the population of ants """
	
	def __init__(self, Scenario, Observer, network):
		""" Creates a population of ants """
		self.Scenario = Scenario
		self.Observer = Observer
		self.popSize = self.Scenario.Parameter('PopulationSize')
		self.network = network
		
		self.Pop = []
		for i in range(self.popSize):
			self.Pop.append(Ant('A%d' % i, network))

		
	def oneStep(self):
		""" This function is repeatedly called by the simulation thread. One ant is randomly chosen and decides what it does. """
		self.Observer.season() # for graphics purpose
		
		ant = random.choice(self.Pop)
		ant.moves()
		Observer.recordChanges(ant.draw())
		
		for link in self.network.draw(): Observer.recordChanges(link) # display best path
		for link in self.network.drawPheromone(): Observer.recordChanges(link) # display pheromone
		
		self.Observer.MsgLength['M1'] = network.currentLength # curve display : length of the current best path
		
		return True # does not stop

		
if __name__ == "__main__":
	print __doc__

	#############################
	# Global objects			#
	#############################
	Gbl = EPar.Parameters('_Params.evo')	# Loading global parameter values
	Observer = Antnet_Observer(Gbl)   # Observer contains statistics
	network = Network(Size=Gbl.Parameter('DisplaySize'), nbNodes=Gbl.Parameter('NumberOfNodes'))
	Pop = Population(Gbl, Observer, network)   # Ant colony
	
	# Initial draw
	Observer.recordInfo('FieldWallpaper', 'yellow')
	Observer.recordChanges(('Dummy',(Gbl.Parameter('DisplaySize'), Gbl.Parameter('DisplaySize'), 0, 1)))	# to resize the field
	for n in network.nodes: Observer.recordChanges(n.draw()) # initial display of the nodes


	EW.Start(Pop.oneStep, Observer, Capabilities='RPC')

	print "Bye......."
	sleep(100.0)
##	raw_input("\n[Return]")

__author__ = 'Samuel Guilhem-Ducleon'
