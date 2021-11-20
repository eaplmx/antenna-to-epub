"""
The MIT License
(c) 2021 eapl.mx

A Python script to read the Gemini Antena feed and grab authorized
URLs into a ePub file

Based on following sources:
https://pypi.org/project/atoma/
https://github.com/aerkalov/ebooklib
https://tildegit.org/solderpunk/gemini-demo-1
"""

# Datetime
import pytz
from datetime import datetime

# Atom Feed parsing
import atoma

# Reading Gemini
import ssl
import cgi
import socket
import tempfile
import urllib.parse

# Gemini to HTML
import re

# ePub
from ebooklib import epub

def absolutise_url(base, relative):
	"""Absolutise relative links."""

	# Based on https://tildegit.org/solderpunk/gemini-demo-1
	if "://" not in relative:
		if 'gemini://' in base:
			# Python's URL tools somehow only work with known schemes?
			base = base.replace("gemini://", "http://")
			relative = urllib.parse.urljoin(base, relative)
			relative = relative.replace("http://", "gemini://")
		if 'http://' in base:
			relative = urllib.parse.urljoin(base, relative)

	return relative

def read_url(url, title='', author=''):
	parsed_url = urllib.parse.urlparse(url)

	try: # Get the Gemini content
		while True:
			s = socket.create_connection((parsed_url.netloc, 1965))
			context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
			context.check_hostname = False
			context.verify_mode = ssl.CERT_NONE
			s = context.wrap_socket(s, server_hostname = parsed_url.netloc)
			s.sendall((url + '\r\n').encode('UTF-8'))

			# Get header and check for redirects
			fp = s.makefile('rb')
			header = fp.readline()
			header = header.decode('UTF-8').strip()
			split_header = header.split()
			status = split_header[0]
			mime = split_header[1]
			# TODO: Fix case when you receive a header like '20 text/gemini; lang=en'

			if status.startswith('1'): # Handle input requests
				query = input('INPUT' + mime + '> ') # Prompt
				url += '?' + urllib.parse.quote(query) # Bit lazy...
			elif status.startswith('3'): # Follow redirects
				url = absolutise_url(url, mime)
				parsed_url = urllib.parse.urlparse(url)
			else: # Otherwise, we're done.
				break
	except Exception as err:
		print(err)
		return

	# Fail if transaction was not successful
	if not status.startswith('2'):
		print(f'Error {status}: {mime}')
		return

	if mime.startswith("text/xml"): # Handle XML Atom feed
		tmpfp = tempfile.NamedTemporaryFile('wb', delete=False)
		feed = atoma.parse_atom_bytes(fp.read())
		
		# TODO: Change this avalanche of ifs
		for entry in feed.entries:
			if (len(entry.links) > 0):
				if initial_date < entry.updated < final_date:
					url_to_read = entry.links[0].href
					in_allowed_urls = False

					for current_url in allowed_urls:
						if current_url in url_to_read:
							in_allowed_urls = True
							break

					if in_allowed_urls:
						print(f'Loading URL: {url_to_read}')
						read_url(url=str(url_to_read), title=entry.title.value, author=entry.authors[0].name)

		tmpfp.write(fp.read())
		tmpfp.close()

		return

	if mime.startswith("text/"):
		# Decode according to declared charset
		mime, mime_opts = cgi.parse_header(mime)
		body = fp.read()
		body = body.decode(mime_opts.get('charset', 'UTF-8'))

		html = convert_to_html(body, url)
		html += f'\n<hr><p><a href={url}>{url}</a></p>'
		
		# Create a chapter in the ePub
		chapter = epub.EpubHtml(title=f'{author}: {title}', file_name=f'chapter_{str(len(chapters)).rjust(3, "0")}.xhtml', lang='en')
		chapter.content = html
		chapters.append(chapter)

# Gemtext to HTML - Code block

# A dictionary that maps regex to match at the beginning of gmi lines
# to their corresponding HTML tag names. Used by convert_single_line().
tags_dict = {
	r"^# (.*)": "h1",
	r"^## (.*)": "h2",
	r"^### (.*)": "h3",
	r"^\* (.*)": "li",
	r"^> (.*)": "blockquote",
	r"^=>\s*(\S+)(\s+.*)?": "a"
}

# This function takes a string of gemtext as input and returns a string of HTML
def convert_single_line(gmi_line, url):
	for pattern in tags_dict.keys():
		if match := re.match(pattern, gmi_line):
			tag = tags_dict[pattern]
			groups = match.groups()

			if tag == "a":
				href = groups[0]
				
				inner_text = str(groups[1]).strip() if len(groups) > 1 else href
				if inner_text == 'None':
					inner_text = href
				
				href = absolutise_url(base=url, relative=href)

				html_a = f"<a href='{href}'>{inner_text}</a>"
				return html_a
			else:
				inner_text = groups[0].strip()
				return f"<{tag}>{inner_text}</{tag}>"
	return f"<p>{gmi_line}</p>"
			
# Reads the contents of the input file line by line and outputs HTML.
# Renders text in preformat blocks (toggled by ```) as multiline <pre> tags.
def convert_to_html(text, url):
	preformat = False
	in_list = False

	html = ''

	for line in text.split('\n'):
		line = line.strip()

		if len(line):
			if line.startswith("```") or line.endswith("```"):
				preformat = not preformat
				repl = "<pre>" if preformat else "</pre>"
				html += re.sub(r"```", repl, line)
			elif preformat:
				html += line
			else:
				html_line = convert_single_line(line, url)
				if html_line.startswith("<li>"):
					if not in_list:
						in_list = True
						html += "<ul>\n"
						
					html += html_line
				elif in_list:
					in_list = False 
					html += "</ul>\n"
					html += html_line
				else:
					html += html_line

		html += '\n'

	return html

# Main code starts here

# Get the date range
# TODO: Ask it from the CLI
year = datetime.now().year
week_num = datetime.now().isocalendar().week

# Get the previous week
# TODO: Fix week_num + 1 error in the last week of the year
week_num -= 1

print('Select week to read on Antenna')
selected_year = input(f'Input year (Enter for {year}): ')
if selected_year.strip() != '':
	try:
		year = int(selected_year)
	except Exception as err:
		print('What kind of year is that?')
		exit()

selected_week = input(f'Input week number (Enter for {week_num}): ')
if selected_week.strip() != '':
	try:
		week_num = int(selected_week)
	except Exception as err:
		print('What kind of week is that?')
		exit()

initial_date = pytz.utc.localize(datetime.fromisocalendar(year, week_num, 1))
final_date = pytz.utc.localize(datetime.fromisocalendar(year, week_num + 1, 1))
print(f'Date range to parse: {initial_date} - {final_date}')

allowed_urls = []
with open('allowed_urls.txt') as f:
	allowed_urls = f.read().splitlines()

book = epub.EpubBook() # Start the ePub library

# Set metadata
book.set_identifier(f'AntennaZINE {year}-w{week_num}')
title = f'AntennaZINE {year}-w{week_num} ({initial_date.strftime("%Y-%m-%d")} to {final_date.strftime("%Y-%m-%d")})'
print(f'Title for the ePub: {title}')

book.set_title(title)
book.set_language('en')
book.add_author('By respective authors')

chapters = [] # Empty list to store every URL into a ePub Chapter

# Read latest entries on Antenna
url = 'gemini://warmedal.se/~antenna/atom.xml'
read_url(url)

# When we've finished reading the allowed URLs, finish the epub
for chapter in chapters:
	book.add_item(chapter)

# Define Table Of Contents
book.toc = chapters

# Add default NCX and Nav file
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# Basic spine
book.spine = ['nav'] + chapters

# Write to the file
epub.write_epub(f'antenna-{year}-w{week_num}.epub', book, {})