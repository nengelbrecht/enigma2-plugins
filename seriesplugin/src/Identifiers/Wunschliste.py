# by betonme @2012

# Imports
from Components.config import config

from Tools.BoundFunction import boundFunction

from urllib import urlencode

from HTMLParser import HTMLParser

from datetime import datetime

import re
from sys import maxint

# Internal
from Plugins.Extensions.SeriesPlugin.IdentifierBase import IdentifierBase
from Plugins.Extensions.SeriesPlugin.Channels import compareChannels
from Plugins.Extensions.SeriesPlugin.Logger import splog

from iso8601 import parse_date

# Constants
SERIESLISTURL     = "http://www.wunschliste.de/ajax/search_dropdown.pl?"
EPISODEIDURLPRINT = "http://www.wunschliste.de/epg_print.pl?"

# (Season.Episode) - EpisodeTitle
# (21.84) Folge 4985
# (105) Folge 105
# (4.11/4.11) Mama ist die Beste/Rund um die Uhr
# Galileo: Die schaerfste Chili der Welt
# Galileo: Jumbo auf Achse: Muelltonnenkoch
# Gute Zeiten, schlechte Zeiten: Folgen 4985 - 4988 (21.84) - Sa 05.05., 11.00:00 Uhr / RTL
#CompiledRegexpPrintTitle = re.compile( '(\(.*\) )?(.+)')

CompiledRegexpEpisode = re.compile( '((\d+)[\.x])?(\d+)')

class WLPrintParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.tr= False
		self.td= False
		self.data = []
		self.list = []

	def handle_starttag(self, tag, attributes):
		if tag == 'td':
			self.td= True
		elif tag == 'tr':
			self.tr= True

	def handle_endtag(self, tag):
		if tag == 'td':
			self.td= False
		elif tag == 'tr':
			self.tr= False
			self.list.append(self.data)
			self.data= []

	def handle_data(self, data):
		if self.tr and self.td:
			self.data.append(data)


class Wunschliste(IdentifierBase):
	def __init__(self):
		IdentifierBase.__init__(self)
		
		self.license = False

	@classmethod
	def knowsToday(cls):
		return True

	@classmethod
	def knowsFuture(cls):
		return True

	def getEpisode(self, name, begin, end=None, service=None, channels=[]):
		# On Success: Return a single season, episode, title tuple
		# On Failure: Return a empty list or String or None
		
		self.begin = begin
		self.end = end
		self.service = service
		self.channels = channels
		
		self.returnvalue = None
		
		# Check preconditions
		if not name:
			splog(_("Skip Wunschliste: No show name specified"))
			return _("Skip Wunschliste: No show name specified")
		if not begin:
			splog(_("Skip Wunschliste: No begin timestamp specified"))
			return _("Skip Wunschliste: No begin timestamp specified")
		
		splog("WunschlistePrint getEpisode")
		
		while name:	
			ids = self.getSeries(name)
			
			while ids:
				idserie = ids.pop()
				
				if idserie and len(idserie) == 2:
					id, self.series = idserie
					
					result = self.getNextPage( id )
					if result:
						return result
					
			else:
				name = self.getAlternativeSeries(name)
		
		else:
			return ( self.returnvalue or _("No matching series found") )

	def getSeries(self, name):
		url = SERIESLISTURL + urlencode({ 'q' : re.sub("[^a-zA-Z0-9*]", " ", name) })
		data = self.getPage( url )
		
		if data and isinstance(data, basestring):
			data = self.parseSeries(data)
			self.doCache(url, data)
		
		if data and isinstance(data, list):
			splog("WunschlistePrint ids", data)
			return data

	def parseSeries(self, data):
		serieslist = []
		for line in data.splitlines():
			values = line.split("|")
			if len(values) == 3:
				idname, countryyear, id = values
				splog(id, idname)
				serieslist.append( (id, idname) )
			else:
				splog("WunschlistePrint: ParseError: " + str(line))
		serieslist.reverse()
		return serieslist

	def parseNextPage(self, data):
		# Handle malformed HTML issues
		#data = data.replace('&quot;','&')
		data = data.replace('&amp;','&')
		parser = WLPrintParser()
		parser.feed(data)
		#splog(parser.list)
		return parser.list

	def getNextPage(self, id):
		splog("WunschlistePrint getNextPage")
		
		url = EPISODEIDURLPRINT + urlencode({ 's' : id })
		data = self.getPage( url )
		
		if data and isinstance(data, basestring):
			data = self.parseNextPage(data)
			self.doCache(url, data)
		
		if data and isinstance(data, list):
			trs = data
			
			yepisode = None
			ydelta = maxint
			year = str(datetime.today().year)
			
			for tds in trs:
				if tds and len(tds) >= 5:
					#print tds
					xchannel, xday, xdate, xbegin, xend = tds[:5]
					xtitle = "".join(tds[4:])
					xbegin   = datetime.strptime( xdate+year+xbegin, "%d.%m.%Y%H.%M Uhr" )
					#xend     = datetime.strptime( xdate+xend, "%d.%m.%Y%H.%M Uhr" )
					#splog(xchannel, xdate, xbegin, xend, xtitle)
					#splog(datebegin, xbegin, abs((datebegin - xbegin)))
					
					#Py2.6
					delta = abs(self.begin - xbegin)
					delta = delta.seconds + delta.days * 24 * 3600
					#Py2.7 delta = abs(self.begin - xbegin).total_seconds()
					splog(self.begin, xbegin, delta, int(config.plugins.seriesplugin.max_time_drift.value)*60)
					
					if delta <= int(config.plugins.seriesplugin.max_time_drift.value) * 60:
						
						if compareChannels(self.channels, xchannel, self.service):
						
							if delta < ydelta:
								
								print len(tds), tds
								if len(tds) >= 7:
									xepisode, xtitle = tds[5:7]
								
									if xepisode:
										result = CompiledRegexpEpisode.search(xepisode)
										
										if result and len(result.groups()) >= 3:
											xseason = result and result.group(2) or "1"
											xepisode = result and result.group(3) or "0"
										else:
											xseason = "1"
											xepisode = "0"
									else:
										xseason = "1"
										xepisode = "0"
								
								elif len(tds) == 6:
									xtitle = tds[5]
									xseason = "0"
									xepisode = "0"
								
								yepisode = (xseason, xepisode, xtitle.decode('ISO-8859-1').encode('utf8'), self.series.decode('ISO-8859-1').encode('utf8'))
								ydelta = delta
							
							else: #if delta >= ydelta:
								break
						
						else:
							self.returnvalue = _("Check the channel name")
						
					elif yepisode:
						break
			
			if yepisode:
				return ( yepisode )