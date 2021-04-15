"""
Discord Screenshot query bot for HCR2.

This is a discord bot for responding to queries regarding matching times that
are found from reading Screenshots of the leaderboard table.
"""

import os
import re

from discord import File, Embed
from discord.ext import commands
from dotenv import load_dotenv

import csv

from datetime import datetime, timedelta
import pytz
import shlex

# Make sure the cwd (Current Working Directory) is the same file directory for saving files in the same place
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

# Load the .env file to get secret token and guild ID for the bot
load_dotenv()
TOKEN = os.getenv('QUERY_DISCORD_TOKEN')
# We're using Discord bot commands framework for this bot
bot = commands.Bot(command_prefix='!')


nameCorrectionPath = "team_name_corrections.csv"
nameCorrectionContainsPath = "team_name_contains_corrections.csv"
nameCorrectionRegexPath = "team_name_regex_corrections.csv"
timezoneShortcutsPath = "timezone_shortcuts.csv"
teamEndTimesPath = "team_end_times.csv"

# Global variables that can easily be changed later
match_length = timedelta(days=2)
datetime_format = "%Y-%m-%dT%H:%M"
time_format = "%H:%M"
utc_tz = pytz.timezone("UTC")
embed_success_color = 0x29AB29
embed_failure_color = 0xFF0000
embed_nodata_color = 0xFF9900


def get_timezone_shortcuts():
    """Return a dictionary of timezone name shortcuts from file."""
    # Read from the csv file for timezone shortcuts and add to the dictionary
    shortcut = {}
    with open(timezoneShortcutsPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            shortcut[row["shortcut"]] = row["timezone"]
    return shortcut


def try_parsing_date(text, tz):
    """Used for validation of user input for creating a datetime object."""
    # Loop over allowed formats to try and find a match (2 available right now)
    for fmt in (datetime_format, "%H:%M"):
        # Try except block to check if the datetime format is allowed
        try:
            # Parse the string into a datetime object using the format being checked
            dt = datetime.strptime(text, fmt)
            # For simple %H:%M format: parsing in that format will automatically set the date to 1900-01-01
            # Therefore, compare with a date much later than that to identify if that format is being used
            # Find the given timezone's local date and replace the year, month and day for this case 
            if datetime.strptime("2000-01-01T00:00", datetime_format) > dt:
                utc_now = pytz.utc.localize(datetime.utcnow())
                local_now = utc_now.astimezone(tz)
                dt = dt.replace(year=local_now.year, month=local_now.month, day=local_now.day)
            # Make the datetime object aware by giving it the timezone information
            dt = tz.localize(dt)
            # Return the final datetime object
            return dt
        # Move on to the next format if this one doesn't parse
        except ValueError:
            pass
    # Return False if the given datetime string doesn't parse with any accepted format
    return False


def get_official_tz(user_tz):
    """Take a timezone string and return a pytz object for use with datetime."""
    official_tz = user_tz
    # Get the list of saved shortcuts from file
    tz_shortcuts = get_timezone_shortcuts()
    # Replace the timezone string with what's saved as the official string for that shortcut
    if official_tz in tz_shortcuts:
        official_tz = tz_shortcuts[user_tz]

    # Return the timezone object if it exists in pytz
    if official_tz in pytz.all_timezones:
        return pytz.timezone(official_tz)
    # Return False if it doesn't exist in pytz
    return False


def split_backtick_aware(inp):
    """Split a string by whitespace, excluding any whitespace enclosed in backticks. Return a list of split strings."""
    lexer = shlex.shlex(inp)
    # Backtick specified as quote character
    lexer.quotes = '`'
    # Single quotation specified as a normal word character
    lexer.wordchars += '\''
    # Split by whitespace
    lexer.whitespace_split = True
    # Comments aren't of any interest here 
    lexer.commenters = ''

    # Create a list out of the split string
    outp = list(lexer)
    # Remove any backticks left behind in any of the actual strings
    for i, word in enumerate(outp):
        outp[i] = word.replace('`', '')

    # Return the final output list
    return outp


def add_tz_func(user_tz, official_tz):
    """Add a custom timezone to the timezone_shortcuts file to make specifying future timestamps easier."""
    # First make sure that the official_tz entered is a valid timezone in pytz. Return a warning string if not. 
    if official_tz not in pytz.all_timezones:
        return embed_failure_color, official_tz + " is not an official timezone. Consult the instructions for more info."
    # Also make sure that the user_tz entered doesn't contain the illegal comma character. Return a warning string if not. 
    if ',' in user_tz:
        return embed_failure_color, "Comma (,) characters are not allowed."
    # Create a list to store all currently stored timezone shortcuts in file and open the file to populate the list
    tz_shortcuts = get_timezone_shortcuts()
    # Add the new shortcut to the dictionary
    tz_shortcuts[user_tz] = official_tz
    # Open the file in write mode and write the whole list of shortcut info to the file
    with open(timezoneShortcutsPath, mode='w', newline='', encoding="utf-8") as tz_data:
        tz_writer = csv.writer(tz_data, delimiter=',')
        # Write the table headings
        tz_writer.writerow(["shortcut", "timezone"])
        # Write the table data for each row
        for key, value in tz_shortcuts.items():
            tz_writer.writerow([key, value])

    ret_str = "Successfully added timezone shortcut " + user_tz + " for " + official_tz
    # Return success feedback string
    return embed_success_color, ret_str


def get_team_end_times_from_file():
    """Get the data from the spreadsheet into a list of dictionaries and return the list."""
    teamEndTimes = []
    with open(teamEndTimesPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            # Append an empty dictionary to the list to be filled with column heading: value pairs
            teamEndTimes.append({})
            # Add each column heading: value pair to the current iteration dictionary that was just appended
            teamEndTimes[i]["position"] = row["position"]
            teamEndTimes[i]["name"] = row["name"]
            teamEndTimes[i]["cups"] = row["cups"]
            teamEndTimes[i]["match against"] = row["match against"]
            teamEndTimes[i]["cup change"] = row["cup change"]
            teamEndTimes[i]["timestamp prior"] = row["timestamp prior"]
            teamEndTimes[i]["timestamp checked"] = row["timestamp checked"]
            teamEndTimes[i]["timestamp changed"] = row["timestamp changed"]
    # Return the list of dictionaries
    return teamEndTimes


def write_new_spreadsheet_data(teamEndTimes):
    """Write the new updated data to the spreadsheet, overwriting the old data."""
    with open(teamEndTimesPath, mode='w', newline='', encoding="utf-8") as team_data:
        team_writer = csv.writer(team_data, delimiter=',')
        # Write the table headings
        team_writer.writerow(["position", "name", "cups", "match against",
                              "cup change", "timestamp prior", "timestamp checked", "timestamp changed"])
        # Write the table data for each row
        for row in teamEndTimes:
            team_writer.writerow([row["position"], row["name"], row["cups"],
                                 row["match against"], row["cup change"], row["timestamp prior"],
                                 row["timestamp checked"], row["timestamp changed"]])


def generate_out(t_data, char_lim=2000):
    """Create a separated output based on a max character limit and present it nicely for Discord."""
    # Start out with an empty string in the output list and a counter for which position the string we're using is in the list
    out_list = [""]
    message_num = 0
    for row in t_data:
        # Create an individual string for each row
        row_string = ""
        # Only use 2 line breaks when it's not the first row in a message
        if out_list[message_num] != "":
            row_string += "\n\n"
        # Position number and team name in code block
        row_string += "`#" + row[0] + "  " + row[1] + "`  "
        # Put a '+' sign in front of cup difference when positive, otherwise negatives can remain as they are
        if not row[2].startswith('-'):
            row_string += "+"
        # Format the time in BOLD and timezone in brackets
        row_string += row[2] + "  **" + row[4] + " - " + row[5] + "** (" + row[6] + ")"
        # Check that data exists for possibly played teams and add it on a new line.
        # Format the description in italics and team names in code block
        if row[3] != "-":
            row_string += "\n*Possibly played:* `" + row[3] + "`"
        
        # Check that adding this row to the current message doesn't cause it to go over the character limit
        if len(out_list[message_num]) + len(row_string) < char_lim:
            # Add the row to the message if it doesn't go over the limit
            out_list[message_num] += row_string
        # Otherwise, create a new message in the list, increase the message counter and add the row to the new message
        else:
            out_list.append("")
            message_num += 1
            out_list[message_num] += row_string
    
    # Output the final list of messages
    return out_list


def get_teams_by_time(dt_string, tz_string):
    """Get every team that finishes at the specified timezone and return as a string."""
    # Get the timezone object from the timezone string and return a warning if it's an invalid timezone
    tz = get_official_tz(tz_string)
    if not tz:
        return embed_failure_color, "Invalid timezone specified. Please check the instructions and use a valid timezone."

    # Get the datetime object from the datetime string and timezone object and return a warning if it's an invalid string format
    dt = try_parsing_date(dt_string, tz)
    if not dt:
        return (embed_failure_color,
            "!time command must be in the format !time timestamp timezone(optional). Consult the instructions for more info.")

    # Specify the +- search range for finding teams ending within the specified time
    search_range = timedelta(hours=1)

    # Get the datetime as UTC for generalisation to work with the data that is stored as UTC
    dt_utc = dt.astimezone(utc_tz)

    # Get the spreadsheet data as a list of dictionaries
    teamEndTimes = get_team_end_times_from_file()

    # Create a list of teams that are within the required range for timestamp changed 
    teamsInRange = []
    for team in teamEndTimes:
        # Get the timestamp objects for end time and the previous check before end time was recorded
        team_end_time = try_parsing_date(team["timestamp changed"], utc_tz)
        team_previous_check = try_parsing_date(team["timestamp prior"], utc_tz)

        # Check that both timestamps are valid (not N/A)
        if team_end_time and team_previous_check:
            # Get the next estimated end time for the team being examined based on a match length 
            team_next_end_time = team_end_time + match_length
            # Check if the end time +- the search range is within the datetime requested and add the team to the list
            if team_next_end_time - search_range <= dt_utc and dt_utc <= team_next_end_time + search_range:
                teamsInRange.append(team)

    
    # If any teams were found in the search range, generate the output string
    if len(teamsInRange) > 0:
        # Initiate the output colour as the command has succeeded with data
        out_color = embed_success_color
        out_string = ""
        tabledata = []
        # Loop over every team identified in range
        for team in teamsInRange:
            # Get the datetime objects of end time and the previous check before end time was recorded in the user's timezone
            team_previous_check_local = try_parsing_date(team["timestamp prior"], utc_tz)
            team_end_time_local = try_parsing_date(team["timestamp changed"], utc_tz)
            team_previous_check_local = team_previous_check_local.astimezone(tz)
            team_end_time_local = team_end_time_local.astimezone(tz)
            ts_from = team_previous_check_local.strftime(time_format)
            ts_to = team_end_time_local.strftime(time_format)
            
            # Generate the output string for the team ending at the given time using the info from the spreadsheet
            out_string += (team["name"] + " in position " + team["position"] + " ended between "
            + team_previous_check_local.strftime(datetime_format) + " and " + team_end_time_local.strftime(datetime_format)
            + " " + tz_string + ", cup difference of " + team["cup change"] + ".")
            # Add extra info about the possible teams this team could have played against last if available,
            # otherwise, this part of the output is skipped
            match_against = "-"
            if team["match against"] != "N/A":
                out_string += " Possibly played against: " + ', '.join(team["match against"].split("¦"))
                match_against = ', '.join(team["match against"].split("¦"))
            
            # End with a newline character for the next team
            out_string += "\n"
            tabledata.append([team["position"], team["name"], team["cup change"], match_against, ts_from, ts_to, tz_string])
        
        out_string = generate_out(tabledata)
    # Otherwise, there aren't any teams in the search range and the output string should reflect that
    else:
        # Initiate the output colour as the command has succeeded but with no data
        out_color = embed_nodata_color
        out_string = "No top teams due to end within the specified time."

    # Return the output string
    return out_color, out_string


def get_time_by_team(team_name, tz_string):
    """Get the time a given team finishes at the specified timezone and return as a string."""
    # Get the timezone object from the timezone string and return a warning if it's an invalid timezone
    tz = get_official_tz(tz_string)
    if not tz:
        return embed_failure_color, "Invalid timezone specified. Please check the instructions and use a valid timezone."

    # Get the spreadsheet data as a list of dictionaries
    teamEndTimes = get_team_end_times_from_file()

    # Check which teams match the searched team_name by searching every team name in the spreadsheet.
    # Search  by looking for names that contain the searched name and add the team to the list of matching_teams  
    matching_teams = []
    for team in teamEndTimes:
        if team_name.lower() in team["name"].lower():
            matching_teams.append(team)

    # If any teams were found in the name search, generate the output string
    if len(matching_teams) > 0:
        # Initiate the output colour as the command has succeeded with data
        out_color = embed_success_color
        out_string = ""
        tabledata = []
        # Loop over every team identified in the search
        for team in matching_teams:
            # Get the datetime objects of end time and the previous check before end time was recorded in the user's timezone
            team_previous_check_local = try_parsing_date(team["timestamp prior"], utc_tz)
            team_end_time_local = try_parsing_date(team["timestamp changed"], utc_tz)
            team_previous_check_local = team_previous_check_local.astimezone(tz)
            team_end_time_local = team_end_time_local.astimezone(tz)
            
            # Get datetime strings from the generated datetime objects
            # If the timestamp is not available for any of the two, the string becomes (unknown)  
            if team_previous_check_local:
                ts_from = team_previous_check_local.strftime(time_format)
            else:
                ts_from = "(unknown)"
            if team_end_time_local:
                
                ts_to = team_end_time_local.strftime(time_format)
            else:
                ts_to = "(unknown)"
            
            # Generate the output string for the team that matches the search using the info from the spreadsheet
            out_string += (team["name"] + " in position " + team["position"] + " ended between "
            + ts_from + " and " + ts_to
            + " " + tz_string + ", cup difference of " + team["cup change"] + ".")
            # Add extra info about the possible teams this team could have played against last if available,
            # otherwise, this part of the output is skipped
            match_against = "-"
            if team["match against"] != "N/A":
                out_string += " Possibly played against: " + ', '.join(team["match against"].split("¦"))
                match_against = ', '.join(team["match against"].split("¦"))
            
            # End with a newline character for the next team
            out_string += "\n"
            tabledata.append([team["position"], team["name"], team["cup change"], match_against, ts_from, ts_to, tz_string])

        out_string = generate_out(tabledata)
    # Otherwise, there aren't any teams that match the search and the output string should reflect that
    else:
        # Initiate the output colour as the command has succeeded but with no data
        out_color = embed_nodata_color
        out_string = "No top teams found with that name."
    
    # Return the output string
    return out_color, out_string


def update_spreadsheet_with_correction(teamEndTimes, wrong_name, correct_name, correction_type):
    """Update the spreadsheet list given with a correction that should be made."""
    teams_to_delete = []
    # Loop over every team in the list to try and find which name matches the search for wrong_name
    for team in teamEndTimes:
        # Depending on the correction type being done, a different search condition is used for each one
        if ((correction_type == "exact" and team["name"] == wrong_name) or
            (correction_type == "contains" and wrong_name in team["name"]) or
            (correction_type == "regex" and re.search(wrong_name, team["name"]))):
            # A different approach is used if there isn't a team that already has the correct name
            correct_name_found = False
            # Loop over every team again to find teams which already have the correct name
            for team2 in teamEndTimes:
                if team2["name"] == correct_name:
                    # Mark down that a team with the correct name has been found
                    correct_name_found = True
                    # Get a datetime object of when the team was last found from both the correct and incorrect team name
                    # "timestamp checked" should always contain a valid datetime string so no need to check for validity
                    wrong_last_checked = try_parsing_date(team["timestamp checked"], utc_tz)
                    correct_last_checked = try_parsing_date(team2["timestamp checked"], utc_tz)
                    wrong_changed = try_parsing_date(team["timestamp changed"], utc_tz)
                    correct_changed = try_parsing_date(team2["timestamp changed"], utc_tz)
                    # Compare to see which name was the latest to be found
                    # If the wrong name was found later than the correct name
                    if wrong_last_checked > correct_last_checked:
                        # Use the correctly named team, using the incorrect team's position and last checked timestamp
                        # The correct team's prior timestamp uses its own timestamp checked from before
                        team2["position"] = team["position"]
                        team2["timestamp prior"] = team2["timestamp checked"]
                        team2["timestamp checked"] = team["timestamp checked"]
                        # To make sure as much as possible is done to reduce "N/A" being used for "timestamp changed",
                        # if the correct name team is being used, the incorrect name's changed value is used if it's
                        # not "N/A" and is more recent than the correct name's value
                        if wrong_changed and correct_changed:
                            if wrong_changed > correct_changed:
                                team2["timestamp changed"] = team["timestamp changed"]
                        elif wrong_changed:
                            team2["timestamp changed"] = team["timestamp changed"]
                        # Check if there's an update in the team's cups
                        if team2["cups"] != team["cups"]:
                            # Work out the change in cups and update that field for the team's record
                            team2["cup change"] = str(int(team["cups"]) - int(team2["cups"]))
                            # Update the cups value to the new, changed cups value
                            team2["cups"] = team["cups"]
                            # Save the new timestamp to the "timestamp changed" field
                            team2["timestamp changed"] = team["timestamp checked"]
                        # Discard the incorrectly named team
                        teams_to_delete.append(team)
                    # Otherwise, the correct name was found later than the wrong name
                    else:
                        # Use the incorrectly named team, using the correct team's position and last checked timestamp
                        # The incorrect team's prior timestamp uses its own timestamp checked from before
                        # The team name also needs to be updated since the  incorrect name is being used
                        team["name"] = correct_name
                        team["position"] = team2["position"]
                        team["timestamp prior"] = team["timestamp checked"]
                        team["timestamp checked"] = team2["timestamp checked"]
                        # To make sure as much as possible is done to reduce "N/A" being used for "timestamp changed",
                        # if the incorrect name team is being used, the correct name's changed value is used if it's
                        # not "N/A" and is more recent than the incorrect name's value
                        if wrong_changed and correct_changed:
                            if correct_changed > wrong_changed:
                                team["timestamp changed"] = team2["timestamp changed"]
                        elif correct_changed:
                            team["timestamp changed"] = team2["timestamp changed"]
                        # Check if there's an update in the team's cups
                        if team["cups"] != team2["cups"]:
                            # Work out the change in cups and update that field for the team's record
                            team["cup change"] = str(int(team2["cups"]) - int(team["cups"]))
                            # Update the cups value to the new, changed cups value
                            team["cups"] = team2["cups"]
                            # Save the new timestamp to the "timestamp changed" field
                            team["timestamp changed"] = team2["timestamp checked"]
                        # Discard the incorrectly named team
                        teams_to_delete.append(team2)
            # Since there isn't a team that already has the correct name,
            # the team with the incorrect name can simply only have its name updated
            if not correct_name_found:
                team["name"] = correct_name
    # Find and remove teams that were marked for deletion earlier
    for team in teams_to_delete:
        if team in teamEndTimes:
            teamEndTimes.remove(team)

    # Deal with adding the data about which teams this team may have played against by having the same cup change
    for team in teamEndTimes:
        TS = team["timestamp changed"]
        # Check if the "timestamp changed" is not a new one by making sure it's not the placeholder N/A
        if TS != "N/A":
            # Find out if the team had a positive or negative cup change
            cupChange = int(team["cup change"])
            if cupChange >= 0:
                posChange = True
            else:
                posChange = False
            against = []
            # Look through the data to find a team that had the same cup change at the same timestamp,
            # that is also not the same team being examined and add it to the "against" list for the team being examined
            for team2 in teamEndTimes:
                if team2["timestamp changed"] == TS and team2["name"] != team["name"]:
                    # Find out if the second team had a positive or negative cup change
                    cupChange2 = int(team2["cup change"])
                    if cupChange2 >= 0:
                        posChange2 = True
                    else:
                        posChange2 = False
                    # Add this second team to the "against" list if it has the opposite polarity to the first team
                    # If a team wins and gains cups, the other team loses cups, and vice-versa
                    if (posChange and not posChange2) or (not posChange and posChange2):
                        against.append(team2["name"])
            # If any possible "against" teams were found, turn the list of them into a string, separated by a reserved character
            # Otherwise, just indicate that the teams that could have played against it are not available
            if len(against) > 0:
                team["match against"] = '¦'.join(against)
            else:
                team["match against"] = "N/A"
    
    # Sort the spreadsheet data by position number
    teamEndTimes.sort(key=lambda team: int(team["position"]))
    
    return teamEndTimes


def add_correction_exact(wrong_name, correct_name):
    """Add a team name correction based on exact match to file and correct any currently in spreadsheet."""
    # Remove illegal characters
    wrong_name = wrong_name.replace(',', '')
    correct_name = correct_name.replace(',', '')
    wrong_name = wrong_name.replace('¦', '')
    correct_name = correct_name.replace('¦', '')
    wrong_name = wrong_name.replace('`', '')
    correct_name = correct_name.replace('`', '')
    # Open the file in append mode and write the correction info to the end of the file
    with open(nameCorrectionPath, mode='a', newline='', encoding="utf-8") as csvfile:
        correction_writer = csv.writer(csvfile, delimiter=',')
        correction_writer.writerow([wrong_name, correct_name])

    # Get the spreadsheet data, update it with the corrections using exact type and write the updated list to the spreadsheet
    teamEndTimes = get_team_end_times_from_file()
    teamEndTimes = update_spreadsheet_with_correction(teamEndTimes, wrong_name, correct_name, "exact")
    write_new_spreadsheet_data(teamEndTimes)

    # Return the output string notifying of the user of successfully adding the correction
    ret_str = "Successfully added exact correction " + wrong_name + " to " + correct_name
    return embed_success_color, ret_str


def add_correction_contains(wrong_name, correct_name):
    """Add a team name correction based on exact match to file and correct any currently in spreadsheet."""
    # Remove illegal characters
    wrong_name = wrong_name.replace(',', '')
    correct_name = correct_name.replace(',', '')
    wrong_name = wrong_name.replace('¦', '')
    correct_name = correct_name.replace('¦', '')
    wrong_name = wrong_name.replace('`', '')
    correct_name = correct_name.replace('`', '')
    # Open the file in append mode and write the correction info to the end of the file
    with open(nameCorrectionContainsPath, mode='a', newline='', encoding="utf-8") as csvfile:
        correction_writer = csv.writer(csvfile, delimiter=',')
        correction_writer.writerow([wrong_name, correct_name])

    # Get the spreadsheet data, update it with the corrections using contains type and write the updated list to the spreadsheet
    teamEndTimes = get_team_end_times_from_file()
    teamEndTimes = update_spreadsheet_with_correction(teamEndTimes, wrong_name, correct_name, "contains")
    write_new_spreadsheet_data(teamEndTimes)

    # Return the output string notifying of the user of successfully adding the correction
    ret_str = 'Successfully added "contains" correction ' + wrong_name + " to " + correct_name
    return embed_success_color, ret_str


def add_correction_regex(pattern, correct_name):
    """Add a team name correction based on exact match to file and correct any currently in spreadsheet."""
    # Remove illegal characters
    correct_name = correct_name.replace(',', '')
    pattern = pattern.replace('¦', '')
    correct_name = correct_name.replace('¦', '')
    pattern = pattern.replace('`', '')
    correct_name = correct_name.replace('`', '')
    # Open the file in append mode and write the correction info to the end of the file
    with open(nameCorrectionRegexPath, mode='a', newline='', encoding="utf-8") as csvfile:
        correction_writer = csv.writer(csvfile, delimiter='¦')
        correction_writer.writerow([pattern, correct_name])

    # Get the spreadsheet data, update it with the corrections using regex type and write the updated list to the spreadsheet
    teamEndTimes = get_team_end_times_from_file()
    teamEndTimes = update_spreadsheet_with_correction(teamEndTimes, pattern, correct_name, "regex")
    write_new_spreadsheet_data(teamEndTimes)

    # Return the output string notifying of the user of successfully adding the correction
    ret_str = "Successfully added RegEx correction for " + pattern + " to " + correct_name
    return embed_success_color, ret_str


@bot.event
async def on_ready():
    """Check that connection to the Discord server has been established."""
    print(f'{bot.user.name} has connected to Discord!')


@bot.command(name="time", help="""Search for top teams supposedly ending at a specified time.\n
Format: !time timestamp timezone(optional)""")
async def time(ctx, *, arg):
    """Handle the !time command."""
    # Use a normal split of space to get each part of the command
    split = arg.split(' ')
    # Prepare the failure output string and color
    out_string = ("!time command must be in the format !time timestamp timezone(optional). " +
                  "Consult the instructions for more info.")
    out_color = embed_failure_color
    # Use UTC timezone if timezone not specified
    if len(split) == 1:
        out_color, out_string = get_teams_by_time(split[0], "UTC")
    # Otherwise, use the specified timezone
    elif len(split) == 2:
        out_color, out_string = get_teams_by_time(split[0], split[1])
    # The output could be a simple string or list of strings if it's possible that the Discord character limit could be exceeded
    # The list of string represents a list of messages, so output each item in a loop
    if isinstance(out_string, str):
        embed_block = Embed(description=out_string, color=out_color)
        await ctx.send(embed=embed_block)
    else:
        for string in out_string:
            embed_block = Embed(description=string, color=out_color)
            await ctx.send(embed=embed_block)


@bot.command(name="team", help="""Search for top teams by name to find when they last ended.\n
Format: !team `team name` timezone(optional)""")
async def team(ctx, *, arg):
    """Handle the !team command."""
    # Use a normal split of space to get each part of the command
    split = split_backtick_aware(arg)
    # Prepare the failure output string and color
    out_string = ("!team command must be in the format !team `team name` timezone(optional)." +
                  "Consult the instructions for more info.")
    out_color = embed_failure_color
    # Use UTC timezone if timezone not specified
    if len(split) == 1:
        out_color, out_string = get_time_by_team(split[0], "UTC")
    # Otherwise, use the specified timezone
    elif len(split) == 2:
        out_color, out_string = get_time_by_team(split[0], split[1])
    # The output could be a simple string or list of strings if it's possible that the Discord character limit could be exceeded
    # The list of string represents a list of messages, so output each item in a loop
    if isinstance(out_string, str):
        embed_block = Embed(description=out_string, color=out_color)
        await ctx.send(embed=embed_block)
    else:
        for string in out_string:
            embed_block = Embed(description=string, color=out_color)
            await ctx.send(embed=embed_block)


@bot.command(name="add_tz", help="""Add a new timezone shortcut that uses an official timezone from tz database.\n
Format: !add_tz new_shortcut official_timezone""")
async def add_tz(ctx, *, arg):
    """Handle the !add_tz command."""
    # Use a normal split of space to get each part of the command
    split = arg.split(' ')
    # Prepare the failure output string and colour
    out_string = ("!add_tz command must be in the format !add_tz new_shortcut official_timezone. " +
                  "Consult the instructions for more info.")
    out_color = embed_failure_color
    # Only accept 2 arguments with new_shortcut and official_timezone
    if len(split) == 2:
        out_color, out_string = add_tz_func(split[0], split[1])
    embed_block = Embed(description=out_string, color=out_color)
    await ctx.send(embed=embed_block)


@bot.command(name="correct", help="""Add a new team name 'exact' correction and update the spreadsheet with the correction.\n
Format: !correct `wrong team name` `correct team name`""")
async def correct(ctx, *, arg):
    """Handle the !correct command."""
    # Use a backtick aware split to get each part of the command with whitespace within backticks ignored
    split = split_backtick_aware(arg)
    # Prepare the failure output string and colour
    out_string = ("!correct command must be in the format !correct `wrong team name` `correct team name`. " +
                  "Consult the instructions for more info.")
    out_color = embed_failure_color
    # Only accept 2 arguments with `wrong team name` and `correct team name`
    if len(split) == 2:
        out_color, out_string = add_correction_exact(split[0], split[1])
    embed_block = Embed(description=out_string, color=out_color)
    await ctx.send(embed=embed_block)


@bot.command(name="correct_contains", help="""Add a new team name 'contains' correction and update the spreadsheet with the 
correction.\n
Format: !correct_contains `wrong team name` `correct team name`""")
async def correct_contains(ctx, *, arg):
    """Handle the !correct_contains command."""
    # Use a backtick aware split to get each part of the command with whitespace within backticks ignored
    split = split_backtick_aware(arg)
    # Prepare the failure output string and  colour
    out_string = ("!correct_contains command must be in the format !correct_contains `wrong team name` " +
                  "`correct team name`. Consult the instructions for more info.")
    out_color = embed_failure_color
    # Only accept 2 arguments with `wrong team name` and `correct team name`
    if len(split) == 2:
        out_color, out_string = add_correction_contains(split[0], split[1])
    embed_block = Embed(description=out_string, color=out_color)
    await ctx.send(embed=embed_block)


@bot.command(name="correct_regex", help="""Add a new team name 'RegEx' correction and update the spreadsheet with the 
correction.\n
Format: !correct_regex `pattern` `correct team name`""")
async def correct_regex(ctx, *, arg):
    """Handle the !correct_regex command."""
    # Use a backtick aware split to get each part of the command with whitespace within backticks ignored
    split = split_backtick_aware(arg)
    # Prepare the failure output string and colour
    out_string = ("!correct_regex command must be in the format !correct_regex `pattern` " +
                  "`correct team name`. Consult the instructions for more info.")
    out_color = embed_failure_color
    # Only accept 2 arguments with `pattern` and `correct team name`
    if len(split) == 2:
        out_color, out_string = add_correction_regex(split[0], split[1])
    embed_block = Embed(description=out_string, color=out_color)
    await ctx.send(embed=embed_block)


@bot.command(name="get_spreadsheet", help="""Send the spreadsheet file in its current state.\n
Format: !get_spreadsheet""")
async def get_spreadsheet(ctx):
    """Handle the !get_spreadsheet command to send a copy of the spreadsheet."""
    # Send the csv file in the Discord channel that the original message was sent
    await ctx.send(file=File(teamEndTimesPath))


# @bot.command(name="test_text", help="""For testing: test what typing in certain text gets you.\n
# Format: !test_text""")
# async def test_text(ctx, *, arg):
#     """Handle the !test_text command to test what a user entering certain text would produce internally."""
#     await ctx.send("Thanks for sending: " + arg)
#     print(arg)


# Run the bot using the Discord bot interface and bot token
bot.run(TOKEN)
