#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  gunnutfinder.py
#
#  Derived from https://github.com/Wyboth/isReactionaryBot, which is
#  Copyright 2015 Wyboth <www.reddit.com/u/Wyboth>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.
#


from privatesettings import password, path, refresh_token
from subreddits import gunnutSubreddits
from logging.handlers import TimedRotatingFileHandler
import logging
import praw
import re
import sqlite3
import sys
import time


class SubredditData:
    """A log of a user's participation in a gun subreddit."""
    subredditName = ''
    submissionCount = 0
    commentCount = 0
    totalSubmissionKarma = 0
    totalCommentKarma = 0
    submissionPermalinks = None  # List cannot be initialized here!
    commentPermalinks = None  # List cannot be initialized here!

    def __init__(self, name, sub_count):
        self.subredditName = name
        self.submissionCount = sub_count


def extract_username(text):
    """Extracts the username from the text of a comment or private message. The bot is summoned on the username found
    immediately after the bot's name."""
    match = username_regex.match(text)
    if match:
        return match.group('username').lower()
    else:
        return None


def has_processed(post):
    """This function returns true if the bot has processed the comment or the private message in question."""
    sqlCursor.execute('SELECT * FROM Identifiers WHERE id=?', (post,))
    if sqlCursor.fetchone() is None:
        return False
    return True


def create_subreddit_summary(subdata):
    """This function creates a SubredditData instance for each gun nut subreddit found in the user's history."""
    datalist = {}
    for subreddit in subdata:
        subdata_instance = SubredditData(subreddit, len(subdata[subreddit]))
        eight_submissions = []
        for submission in subdata[subreddit]:
            subdata_instance.totalSubmissionKarma += submission[1]
            if len(eight_submissions) < 8:
                eight_submissions.append(submission[0])
        subdata_instance.submissionPermalinks = []
        for submission in eight_submissions:
            subdata_instance.submissionPermalinks.append(r.get_info(thing_id=submission).permalink)
        datalist[subreddit] = subdata_instance
    return datalist


def add_comment_data(subreddit_summary, commentdata):
    """This function adds the comments from each gun nut subreddit to the list thus far compiled."""
    datalist = {}
    for subreddit in commentdata:
        if subreddit in subreddit_summary:
            subdata_instance = subreddit_summary[subreddit]
        else:
            subdata_instance = SubredditData(subreddit, 0)
        eight_comments = []
        for comment in commentdata[subreddit]:
            subdata_instance.commentCount += 1
            subdata_instance.totalCommentKarma += comment[1]
            if len(eight_comments) < 8:
                eight_comments.append(comment[0])
        subdata_instance.commentPermalinks = []
        for comment in eight_comments:
            subdata_instance.commentPermalinks.append(r.get_info(thing_id=comment).permalink)
        datalist[subreddit] = subdata_instance
    return datalist


def calculate_gunnuttiness(user):
    """Figures out how much of a gun nut the user is, and returns the reply text."""
    subreddit_summary = {}

    praw_user = r.get_redditor(user)
    username = praw_user.name
    submissions = praw_user.get_submitted(limit=1000)
    comments = praw_user.get_comments(limit=1000)

    subdata = {}
    for submission in submissions:
        subreddit = submission.subreddit.display_name.lower()
        if subreddit in gunnutSubreddits:
            if subreddit in subdata:
                subdata[subreddit].append((submission.fullname, int(submission.score)))
            else:
                subdata[subreddit] = [(submission.fullname, int(submission.score))]
    if subdata:
        subreddit_summary.update(create_subreddit_summary(subdata))

    commentdata = {}
    for comment in comments:
        subreddit = comment.subreddit.display_name.lower()
        if subreddit in gunnutSubreddits:
            if subreddit in commentdata:
                commentdata[subreddit].append((comment.fullname, int(comment.score)))
            else:
                commentdata[subreddit] = [(comment.fullname, int(comment.score))]
    if commentdata:
        subreddit_summary.update(add_comment_data(subreddit_summary, commentdata))

    if not subreddit_summary:
        return 'Nothing found for ' + username + '.'

    score = 0
    replytext = username + ' post history contains participation in the following subreddits:\n\n'
    for subreddit in subreddit_summary:
        replytext += '/r/' + subreddit_summary[subreddit].subredditName + ': '
        if subreddit_summary[subreddit].submissionPermalinks:
            replytext += str(subreddit_summary[subreddit].submissionCount) + ' posts ('
            for i in range(len(subreddit_summary[subreddit].submissionPermalinks)):
                replytext += '[' + str(i + 1) + '](' + subreddit_summary[subreddit].submissionPermalinks[i] + '), '
            replytext = replytext[:-2] + '), **combined score: ' + str(subreddit_summary[subreddit].totalSubmissionKarma) + '**'
            if subreddit_summary[subreddit].commentPermalinks:
                replytext += '; '
        if subreddit_summary[subreddit].commentPermalinks:
            replytext += str(subreddit_summary[subreddit].commentCount) + ' comments ('
            for i in range(len(subreddit_summary[subreddit].commentPermalinks)):
                replytext += '[' + str(i + 1) + '](' + subreddit_summary[subreddit].commentPermalinks[i] + '), '
            replytext = replytext[:-2] + '), **combined score: ' + str(subreddit_summary[subreddit].totalCommentKarma) + '**'
        replytext += '.\n\n'
        score += subreddit_summary[subreddit].totalSubmissionKarma + subreddit_summary[subreddit].totalCommentKarma
        if len(replytext) >= 9500:
            break

    replytext += '---\n\n###Total score: ' + str(score) + '\n\n###Chance of being a gunnut: '
    if score > 0:
        replytext += str((score + 1) ** 3) + '%.'
    else:
        replytext += '0%.'
    replytext += '\n\n---\n\nI am a bot. Only the past 1,000 posts and comments are fetched. If I am misbehaving send' \
                 'my [Creator](https://np.reddit.com/message/compose/?to=sasnfbi1234) a message.'
    return replytext


def handle_request(request):
    """Handles a user's comment or private message requesting the bot to investigate a user's gunnuttiness."""
    if not has_processed(request.id):
        user = extract_username(request.body)
        if user is not None:
            try:
                if user == 'gunnutfinder':  # For smartasses.
                    request.reply('Nice try.')
                    sqlCursor.execute('INSERT INTO Identifiers VALUES (?)', (request.id,))
                    logger.info('Received request to check self.')
                else:
                    request.reply(calculate_gunnuttiness(user))
                    sqlCursor.execute('INSERT INTO Identifiers VALUES (?)', (request.id,))
                    logger.info('Received and successfully processed request to check user {0}'.format(user))
            except praw.errors.NotFound:
                request.reply('User {0} not found.'.format(user))
                sqlCursor.execute('INSERT INTO Identifiers VALUES (?)', (request.id,))
                logger.info('Received request to check user {0}. Failed to find user.'.format(user))
            except praw.errors.Forbidden:
                sqlCursor.execute('INSERT INTO Identifiers VALUES (?)', (request.id,))
                logger.info('Received request to check user {0}. Received 403 (probably banned).'.format(user))
            sqlConnection.commit()


def main():
    r.refresh_access_information(refresh_token)
    while True:
        try:
            for mention in r.get_mentions():
                handle_request(mention)
            for message in r.get_messages():
                handle_request(message)
        except praw.errors.HTTPException:
            pass
        except Exception:
            logger.exception('Error: ')
            continue
        time.sleep(120)


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('gnutlogger')
loghandler = TimedRotatingFileHandler(path + 'log.txt', when='d', backupCount=3)
loghandler.setLevel(logging.INFO)
logformat = logging.Formatter(fmt='%(asctime)s: %(levelname)s: %(message)s',
                              datefmt='%m/%d/%Y %I:%M:%S %p')
loghandler.setFormatter(logformat)
logger.addHandler(loghandler)

username_regex = re.compile(r'^(/u/gunnutfinder)?\s*(?:/?u/)?(?P<username>\w+)\s*$', re.IGNORECASE | re.MULTILINE)

sqlConnection = sqlite3.connect(path + 'database.db')
sqlCursor = sqlConnection.cursor()
sqlCursor.execute('CREATE TABLE IF NOT EXISTS Identifiers (id text)')

r = praw.Reddit(user_agent='A program that checks if a user is a gun nut.', site_name='gnutfinder')

if __name__ == '__main__':
    main()
