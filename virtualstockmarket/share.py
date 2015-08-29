#!/usr/bin/env python
#coding: utf-8
import praw
import OAuth2Util
import json
import re
import os
import logging
import sys
import time
import pickle

class STOCKS:
	def __init__(self, subreddit):
        self.r = praw.Reddit("/r/BRSE stock automation by /u/b0wmz")
		path = os.path.realpath(__file__)
		path = path.replace(os.path.basename(__file__), "")
		self._o = OAuth2Util.OAuth2Util(self.r, configfile=path+"oauth.txt")

		self.subreddit = self.r.get_subreddit(subreddit)
		self.prices = {} #share prices
		self.credit = {} #users individual balance for traditional buy/sell
		self.shares = {} #users individual shares
		self.margin = {} #user's margin balance for option trading
		with open(path+"doneposts", "rb") as file:
			self.doneposts = pickle.load(file)

		self.log = logging.getLogger("main")
		formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		ch = logging.StreamHandler(sys.stdout)
		ch.setLevel(logging.DEBUG)
		ch.setFormatter(formatter)
		self.log.addHandler(ch)
		fh = logging.FileHandler("share.log")
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(formatter)
		self.log.addHandler(fh)
		self.log.setLevel(logging.DEBUG)

		try:
			self.currentpost = self.r.get_sticky(self.subreddit)
			self.log.info("Attempting to load ALL comments ...")
			self.currentpost.replace_more_comments()
			self.log.info("Loaded all comments successfully")
		except praw.errors.NotFound:
			self.log.critical("No sticky found, aborting.")
			exit()

#	Load current prices from /wiki/prices
	def getSharePrices(self):
		page = self.r.get_wiki_page(self.subreddit, "prices").content_md
		for idx,val in json.loads(page).iteritems():
			self.prices[idx] = val['Value']
		self.log.debug("Loaded share prices")
#	Load all user balances from /wiki/credit
	def getUsersCredit(self):
		credit = json.loads(self.r.get_wiki_page(self.subreddit, "credit").content_md)
		for idx, val in credit.iteritems():
			self.credit[idx] = val["Balance"]
			self.margin[idx] = val["Margin"]
		self.log.debug("Loaded user credit")
#	Get balance for specified user		
	def getUserCredit(self, username):
		for idx, val in self.credit.iteritems():
			if idx == username:
				return val
#	Get shareholdings for specified user
	def getUserShares(self, username):
		for idx, val in self.shares.iteritems():
			if idx == username:
				return val
#	Load all shareholdings from /wiki/shares
	def getTotalShares(self):
		self.shares = json.loads(self.r.get_wiki_page(self.subreddit, "shares").content_md)
		self.log.debug("Loaded user shares")
#	Calculate and return remaining balance
	def creditUserShare(self, username, asset, amount):
#		Check if user has an open account
		try:
			balance = self.credit[username]
#		If one does not exist, create one with a starting balance of 1000 credits
#		(Is this missing a return statement, or is it unnecessary?)
		except KeyError:
			self.credit[username] = 1000
			self.credit[margin] = 0
			self.log.info("Created share account for %s. Starting balance %d" % (username, self.credit[username]))
#		Attempt transaction
		try:
			balance = self.credit[username]
			share_price = self.prices[asset]
			debit = amount * share_price
#			Deny trade if balance is less than trade price			
			if balance - debit < 0:
				return "nocash"
#			Attempt sale if request is negative number
			if amount < 0:
				try:
					sale_amount = -amount #Convert sale to positive number of shares
#					Deny sale if user doesn't have enough shares
					if sale_amount > self.shares[username][asset]: 
						return "noshares"
#				Deny if user doesn't own asset
				except KeyError:
					return "noshares"
#			If successful, subtract asset price from balance
			balance -= debit
#			Log debit
			self.log.info(
				"User %s purchased %d of %s at %d each. Total sale of %d. Balance remaining: %d" % (
					username, amount, asset, share_price, debit, balance
				)
			)
		except KeyError:
			debit = amount * self.prices[asset]
			if debit > balance:
				self.log.error("%s doesn't have enough money to buy %d shares of %s" % (username, amount, asset))
				return "nocash"
			self.credit[username] = balance - debit
			self.margin[username] = ""
			self.log.info(
				"Created share account for %s and removed %d. Total is now %d. Individual price for share %s %d" % (
					username, debit, balance, asset, self.prices[asset]
				)
			)
			return self.credit[username]

#	Check comments for transaction commands
	def parseComments(self):
		try:
			for c in self.currentpost.comments:
				if c.id in self.doneposts:
					self.log.debug("Not checking post %s, since already checked" % c.id)
					continue
				if c.edited is True:
					self.log.debug("Post %s id edited, skipping" % c.id)
					self.doneposts.append(c.id)
					c.reply("Post is edited, ignoring.")
					continue
				action = c.body.split()
				self.log.debug(c.body)
#				Ignore comments that don't start with proper commands
				if action[0].lower() != "buy" and action[0].lower() != "sell":
					self.log.info("Post isn't buy/sell post, ignoring %s" % c.id)
					self.doneposts.append(c.id) #ignore post in the future
					continue
#				Inform user of improper code and skip post
				try:
					action[1] = action[1].upper()
					self.log.debug(self.prices[action[1]])
				except KeyError:
					reply = "Invalid Code %s" % action[1]
					self.log.error(reply)
					self.doneposts.append(c.id) #ignore post in the future
					c.reply(reply)
					continue

				try:
					action[2] = int(action[2])
				except ValueError:
					reply = "Invalid amount specified"
					self.log.error(reply)
					self.doneposts.append(c.id) #ignore post in the future
					c.reply(reply)
					continue

				if action[0].lower() == "buy":
					remaining = self.creditUserShare(str(c.author), action[1], action[2])
					self.addUserShares(str(c.author), action[1], action[2])
				elif action[0].lower() == "sell":
					remaining = self.creditUserShare(str(c.author), action[1], -action[2])
					self.addUserShares(str(c.author), action[1], -action[2])
				else:
					reply = "Invalid action %s. Valid actions are BUY and SELL." % action[0]
					self.log.error(reply)
					self.doneposts.append(c.id)
					c.reply(reply)
					continue

				try:
					int(remaining)
					self.doneposts.append(c.id)
					c.reply("Trade confirmed. **Balance %d cr.**" % remaining)
				except ValueError:
					if remaining == "nocash":
						self.doneposts.append(c.id)
						c.reply("You do not have enough money to make this trade.")
						continue
					elif remaining == "noshares":
						self.doneposts.append(c.id)
						c.reply("You do not have this many shares.")
						continue

				self.doneposts.append(c.id)
					
		except Exception, e:
			self.log.exception(e)

	# self.shares["example"] = {"ZUL": 5, "AME": 5}
	def addUserShares(self, username, share, amount):
		try: #user's share exists
			self.shares[username]
			self.log.debug("User's share exists %s" % username)
			try: #share exists
				self.shares[username][share]+=amount
				self.log.debug("Share %s exists in user %s" % (share, username))
				self.log.info("Added %d shares to %s's %s account" % (amount, username, share))
			except KeyError: #share doesn't exist
				self.shares[username][share] = amount
				self.log.debug("%s's account exists, created %s share" % (username, share))
				self.log.info("Added %d shares to %s's %s account" % (amount, username, share))
		except KeyError:
			self.shares[username] = {share: amount}
			self.log.debug("%s's account doesn't exist, created" % username)
			self.log.info("Added %d shares to %s's %s account" % (amount, username, share))


	def writeContent(self):
		sortedShares = sorted(self.shares, 
		self.r.edit_wiki_page(self.subreddit, "shares", json.dumps(self.shares), "Set new shares")
		credit = {}
		for idx,val in self.credit.iteritems():
			try:
				self.margin[idx]
			except KeyError:
				self.margin[idx] = None
			credit[idx] = {"Balance": val, "Margin": self.margin[idx]}
		self.r.edit_wiki_page(self.subreddit, "credit", json.dumps(credit), "Set new credit")

		with open("doneposts", "wb") as file:
			pickle.dump(self.doneposts, file)

		self.log.debug("Saved everything")

	def main(self):
		self.getSharePrices()
		self.getUsersCredit()
		self.getTotalShares()
		self.parseComments()
		time.sleep(2)
		self.writeContent()

if __name__ == "__main__":
	s = STOCKS("")
	s.main()
