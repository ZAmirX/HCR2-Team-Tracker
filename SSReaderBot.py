"""
Discord Screenshot reader for HCR2.

This is a discord bot for reading Screenshots and saving the information to a
spreadsheet csv file.
"""

import os
import re

import discord
from dotenv import load_dotenv

from PIL import Image
import cv2
import numpy as np

import pytesseract
import csv

import aiohttp
import io

from datetime import datetime
import pytz

# Make sure the cwd (Current Working Directory) is the same file directory for saving files in the same place
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

# Add the directory for Tesseract
tesseractPath = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
pytesseract.pytesseract.tesseract_cmd = tesseractPath

# Change the name corrections and spreadsheet file locations here if necessary
nameCorrectionPath = "team_name_corrections.csv"
nameCorrectionContainsPath = "team_name_contains_corrections.csv"
nameCorrectionRegexPath = "team_name_regex_corrections.csv"
timezoneShortcutsPath = "timezone_shortcuts.csv"
teamEndTimesPath = "team_end_times.csv"

# The main format for using both date and time
datetime_format = "%Y-%m-%dT%H:%M"
# embed colours that will be used in output messages
embed_success_color = 0x29AB29
embed_failure_color = 0xFF0000
embed_nodata_color = 0xFF9900

# Load the .env file to get secret token and guild ID for the bot
load_dotenv()
TOKEN = os.getenv('READER_DISCORD_TOKEN')
# We're using Discord client framework for this bot so we can use on_message
client = discord.Client()


# The following functions will be used to correct OCR data as much as possible
def remove_extra_newline(string):
    """Remove any double newlines that shouldn't exist."""
    newstr = ""
    i = 0
    while i < len(string)-1:
        newstr += string[i]
        if string[i] == '\n' and string[i+1] == '\n':
            i += 2
        else:
            i += 1
    return newstr


def remove_dotNcomma(string):
    """Remove any dot and comma in a string."""
    string = string.replace('.', '')
    string = string.replace(',', '')
    return string


def remove_space(string):
    """Remove all spaces in a string."""
    string = string.replace(' ', '')
    return string


def remove_formfeed(string):
    """Remove all form feed characters in a string."""
    string = string.replace('\f', '')
    return string


def change_reserved_characters(string):
    """Change any reserved characters for processing to similar characters."""
    """List consists of: ¦ to | and , to . and ` to '"""
    string = string.replace('¦', '|')
    string = string.replace(',', '.')
    string = string.replace('`', "'")
    return string


# The main image processing function that uses Tesseract OCR to get text from image
async def SS_extract_text(imgcv):
    """Take an OpenCV image and extract the text from the columns."""
    # Get the height and width of the image to crop it
    height, width = imgcv.shape[:2]

    # The top of the image to crop out seems constant for different resolutions after testing a range of resolutions
    topTrim = int(0.337 * height)
    imgcv = imgcv[topTrim:height, 0:width]

    # Invert the image to get black text on white background
    imginvert = cv2.bitwise_not(imgcv)
    # Grayscale the image to prepare for binarisation
    grayImage = cv2.cvtColor(imginvert, cv2.COLOR_BGR2GRAY)
    # Threshold the image to binarise the image for only black or white pixels
    _, BWcv2img = cv2.threshold(grayImage, 110, 255, cv2.THRESH_BINARY)

    # Get the new height and width of the cropped image
    height, width = BWcv2img.shape[:2]
    # Invert the image to prepare for dilation
    BWcv2imgInv = cv2.bitwise_not(BWcv2img)
    # Use a 5*5 kernel to dilate the image
    kernel = np.ones((5, 5), np.uint8)
    # Dilate the image using the kernel, doing so with a tested 10 iterations to mix characters together
    dilated = cv2.dilate(BWcv2imgInv, kernel, iterations=10)
    # Also use a kernel to mix together the rows to make one long column
    # Kernel stretches vertically by height/8 as there should be 9 rows, making it stretch by slightly more than 1 row height
    vertical_row_mix_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize=(1, int(height / 8)))

    # Dilate the already dilated image with the vertical stretching kernel to mix rows into long columns
    colCheckDilate = cv2.dilate(dilated, vertical_row_mix_kernel)

    # Find the contours in the column check dilated image to verify it's a column we're looking for
    colCheckContours, _ = cv2.findContours(colCheckDilate, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Loop through every proposed column and add to mid point in the x direction of every column that's at least 90%
    # of the image height to a list for checking later
    colMidPts = []
    for col in colCheckContours:
        x, y, w, h = cv2.boundingRect(col)
        if h > (0.9 * height):
            leftSide = x
            rightSide = x + w
            midPt = (leftSide + rightSide) / 2
            colMidPts.append(midPt)

    # Make a vertical kernel that's sure to span the entire height of the image even if the pixel is at the top/bottom of image
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize=(1, 2 * height))
    # Dilate the image using the new vertical kernel to get every possible column
    dilated = cv2.dilate(dilated, vertical_kernel)
    # Get the contours of this new dilated image of columns
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    goodCol = False
    cntNum = 0
    # Loop through each contour representing a column and decide if it should be used
    for cnt in contours:
        # Get the bounds of the contour
        x, y, w, h = cv2.boundingRect(cnt)
        # Make sure this is an acceptable column by checking the mid points of acceptable columns is within
        # the bounds of the contour along the x axis
        for Pt in colMidPts:
            if Pt > x and Pt < (x + w):
                goodCol = True
                break
        # Once identified as a good column, process each one individually, depending column number
        if goodCol:
            # First column is the team cups
            if cntNum == 0:
                # Crop contour size out of binary image and put into variable as image
                cups_img = BWcv2img[y:y+h, x:x+w]
                cntNum += 1
            # Second column is images of a cup, so should be ignored
            elif cntNum == 1:
                cntNum += 1
            # Third column is team names
            elif cntNum == 2:
                # Crop contour size out of binary image and put into variable as image
                names_img = BWcv2img[y:y+h, x:x+w]
                # Inverse black and white in the image
                names_img_inv = cv2.bitwise_not(names_img)
                # Make a new kernel for full horizontal dilation of image. 7 px height was chosen through testing
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize=(2 * w, 7))
                # Dilate using the horizintal kernel to get each row as a contour
                names_img_rows = cv2.dilate(names_img_inv, horizontal_kernel)
                # Extract the contours out of the dilated image to find each row's bounds
                NameRowContours, _ = cv2.findContours(names_img_rows, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                # Reverse to get each row from top to bottom rather than bottom to top
                NameRowContours.reverse()

                # Create the blank mask to be written to with all contours to be removed
                cleanupMask = np.ones(names_img.shape[:2], dtype="uint8") * 255
                # Get every contour (letter/shape) in the names_img
                NameContours, _ = cv2.findContours(names_img_inv, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                # Reverse to get the contours in the right order
                NameContours.reverse()

                # Loop through each contour found and find the left, right, top and bottom most pixel locations of that contour
                charLocation = []
                for charCnt in NameContours:
                    charLeft = tuple(charCnt[charCnt[:, :, 0].argmin()][0])
                    charRight = tuple(charCnt[charCnt[:, :, 0].argmax()][0])
                    charTop = tuple(charCnt[charCnt[:, :, 1].argmin()][0])
                    charBottom = tuple(charCnt[charCnt[:, :, 1].argmax()][0])
                    # Loop through each row found by contour and get the top and bottom most pixels of that row contour
                    for row in NameRowContours:
                        rowTop = tuple(row[row[:, :, 1].argmin()][0])
                        rowBottom = tuple(row[row[:, :, 1].argmax()][0])
                        # Add the character contour extreme bounds to the list, with the top and bottom bounds of the row it's in
                        if charTop[1] >= rowTop[1] and charTop[1] <= rowBottom[1]:
                            charLocation.append((charLeft, charRight, charTop, charBottom, rowTop, rowBottom))

                # Loop through each contour again, just like before, to decide if it should be removed this time
                for charCnt in NameContours:
                    charLeft = tuple(charCnt[charCnt[:, :, 0].argmin()][0])
                    charRight = tuple(charCnt[charCnt[:, :, 0].argmax()][0])
                    charTop = tuple(charCnt[charCnt[:, :, 1].argmin()][0])
                    charBottom = tuple(charCnt[charCnt[:, :, 1].argmax()][0])
                    # Loop though each identified character contour found earlier
                    for idenCharRow in charLocation:
                        # Make sure it's not the same character contour being examined
                        if charLeft != idenCharRow[0] and charRight != idenCharRow[1] and charTop != idenCharRow[2] and charBottom != idenCharRow[3]:
                            # Find out if it's an overlapping contour on right side
                            # Within same row \ right side of character overlaps another character \
                            # less than 2 pixels wider on either side than other character
                            if charTop[1] >= idenCharRow[4][1] and charBottom[1] <= idenCharRow[5][1] \
                                    and charRight[0] >= idenCharRow[0][0] and charRight[0] <= idenCharRow[1][0] \
                                    and (charLeft[0] < idenCharRow[0][0] - 2 or charRight[0] > idenCharRow[1][0] + 2):
                                cv2.drawContours(cleanupMask, [charCnt], -1, 0, -1)

                # Add the mask to the original image
                names_img_inv = cv2.bitwise_and(names_img_inv, names_img_inv, mask=cleanupMask)

                # Find tiny pixels left over and remove them (with area less than 5)
                NameContours, _ = cv2.findContours(names_img_inv, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                for nameCnt in NameContours:
                    area = cv2.contourArea(nameCnt)
                    if area < 5:
                        cv2.drawContours(cleanupMask, [nameCnt], -1, 0, -1)
                # Add this mask to the original image
                names_img_inv = cv2.bitwise_and(names_img_inv, names_img_inv, mask=cleanupMask)

                # Find first pixel location for each row
                firstPxRow = []
                for row in NameRowContours:
                    # Get the top and bottom most pixels of the row contour
                    rowTop = tuple(row[row[:, :, 1].argmin()][0])
                    rowBottom = tuple(row[row[:, :, 1].argmax()][0])
                    # Crop out the row to use
                    array = names_img_inv[rowTop[1]:rowBottom[1], 0:w]
                    # Rotate it so that the first relevant pixel is found by column
                    array = np.rot90(array, 3)
                    # Find the first white pixel in the inversed image
                    white_pixels = np.array(np.where(array == 255))
                    first_white_pixelX = white_pixels[:, 0][0]
                    # Add this pixel location's x coordinate to the list
                    firstPxRow.append(first_white_pixelX)

                # Perform cluster analysis to find the most common first x coordinate within a certain range
                maxgap = 3
                firstPxRow.sort()
                groups = [[firstPxRow[0]]]
                for x in firstPxRow[1:]:
                    if abs(x - groups[-1][-1]) <= maxgap:
                        groups[-1].append(x)
                    else:
                        groups.append([x])
                # Get the index of the largest group in the groups list
                lists_len = [len(i) for i in groups]
                groups_index = np.argmax(np.array(lists_len))

                # Get the first most common pixel found earlier
                firstPx = min(groups[groups_index])
                # Create a mask covering until the first most common pixel
                rectMask = np.ones(names_img.shape[:2], dtype="uint8") * 255
                cv2.rectangle(rectMask, (0, 0), (firstPx, h), 0, -1)
                # Add this mask to the original image
                names_img_inv = cv2.bitwise_and(names_img_inv, names_img_inv, mask=rectMask)

                # Return the image to black text on white background
                names_img = cv2.bitwise_not(names_img_inv)

                cntNum += 1
            # Fourth column is team position number
            elif cntNum == 3:
                # Crop contour size out of binary image and put into variable as image
                positions_img = BWcv2img[y:y+h, x:x+w]
                # Remove the team badges

                # Inverse the image ready for dilation
                positions_imgInv = cv2.bitwise_not(positions_img)
                # Dilate using the normal kernel to merge characters
                posDilated = cv2.dilate(positions_imgInv, kernel)
                # Dilate using the vertical kernel to get separate columns
                posDilated = cv2.dilate(posDilated, vertical_kernel)
                # Find the contours of each column
                posContours, _ = cv2.findContours(posDilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                # Get the column bounds for the first coumn as second column is just team badges
                x, y, w, h = cv2.boundingRect(posContours[0])
                # Crop out and use the contour bounds for the image as the positions_img
                positions_img = positions_img[y:y+h, x:x+w]
                cntNum += 1
        # Reset the identification of a good column
        goodCol = False

    color_coverted = cv2.cvtColor(cups_img, cv2.COLOR_BGR2RGB)
    cups_img = Image.fromarray(color_coverted)
    color_coverted = cv2.cvtColor(names_img, cv2.COLOR_BGR2RGB)
    names_img = Image.fromarray(color_coverted)
    names_img.save("names_img.png")
    color_coverted = cv2.cvtColor(positions_img, cv2.COLOR_BGR2RGB)
    positions_img = Image.fromarray(color_coverted)
    positions_img.save("positions_img.png")

    # Get the text from the positions image, using psm 6 for vertical block of text,
    # including only number digits and . in result, while also using the specificaly trained HCR2 font as primary language
    positions_txt = pytesseract.image_to_string(positions_img, config='--psm 6 -c tessedit_char_whitelist=0123456789. -l HCR2+eng')
    # Remove the extra unwanted characters in the output
    positions_txt = remove_formfeed(positions_txt)
    positions_txt = remove_space(positions_txt)
    positions_txt = remove_dotNcomma(positions_txt)
    # Put the result in a list by splitting the string by newlines
    positions_list = positions_txt.splitlines()

    # Get the text from the names image, using psm 6 for vertical block of text,
    # while using the specificaly trained HCR2 font as primary language
    names_txt = pytesseract.image_to_string(names_img, config='--psm 6 -l HCR2+eng')
    # Remove the extra unwanted characters in the output
    names_txt = remove_formfeed(names_txt)
    names_txt = remove_extra_newline(names_txt)
    # Change reserved characters that will need to be used for post processing only
    names_txt = change_reserved_characters(names_txt)
    # Put the result in a list by splitting the string by newlines
    names_list = names_txt.splitlines()

    # Get the text from the cups image, using psm 6 for vertical block of text,
    # including only number digits in result, while also using the specificaly trained HCR2 font as primary language
    cups_txt = pytesseract.image_to_string(cups_img, config='--psm 6 -c tessedit_char_whitelist=0123456789 -l HCR2')
    # Remove the extra unwanted characters in the output
    cups_txt = remove_formfeed(cups_txt)
    cups_txt = remove_space(cups_txt)
    # Put the result in a list by splitting the string by newlines
    cups_list = cups_txt.splitlines()

    # Handle the function output
    # The number of lines for each column needs to match, otherwise an error needs to be returned
    if len(positions_list) == len(names_list) == len(cups_list):
        # Merge all 3 columns into one list of dictionaries specifying each column name as key and instance as value
        team_row_list = []
        for teamNum in range(0, len(positions_list)):
            team_row_list.append({"position": positions_list[teamNum], "name": names_list[teamNum], "cups": cups_list[teamNum]})
        return team_row_list
    else:
        raise Exception("Uneven rows were found.")


def fixDupTeamNames(team_list, num=1, name="N/A"):
    """Deals with any duplicate team names in the dataset."""
    # Nested loop for same list to find any duplicates
    for i, team in enumerate(team_list):
        for j, team2 in enumerate(team_list):
            # Duplicate if the names are the same but not the same row being examined
            if team["name"] == team2["name"] and i != j:
                # If we've come across the same team name that's been dealt with before, add a 1 to the previous number
                if name == team["name"]:
                    team2["name"] = team2["name"] + str(num + 1)
                    # Recursive call to find another duplicate team
                    team_list = fixDupTeamNames(team_list, num + 1, team["name"])
                # Otherwise, it's a new duplicate team name and so a 2 needs to be put at the end
                else:
                    team2["name"] = team2["name"] + str(2)
                    # Recursive call to find another duplicate team, with current number 2 as first duplicate
                    team_list = fixDupTeamNames(team_list, 2, team["name"])
    # Return the final team list with no duplicates
    return team_list


def group(L):
    """Sort a list of integers into consecutive numbers and return the list of start and end numbers for each group."""
    first = last = L[0]
    for n in L[1:]:
        if n - 1 == last:  # Part of the group, bump the end
            last = n
        else:  # Not part of the group, yield current group and start a new
            yield first, last
            first = last = n
    yield first, last  # Yield the last group


def consectutive_group_to_string(l):
    """Use the group function to get the list of groups and turn it into a readable string."""
    out_string = "Successfully added data on teams in positions"
    grouped_list = group(l)
    for i, rnge in enumerate(grouped_list):
        # If not first range then we need a separator inserted in the string
        if i != 0:
            out_string += " and"
        # Check if it's an actual range or a single digit and insert into the string
        if rnge[0] != rnge[1]:
            out_string += " " + str(rnge[0]) + "-" + str(rnge[1])
        else:
            out_string += " " + str(rnge[0])
    # End the string with a dot
    out_string += "."
    # Return the final string
    return out_string


def find_inconsecutive_in_dict_list(l, dict_key, descending=False):
    """Find position of dictionaries in a list that aren't in ascending/descending order."""
    """Note that this assumes first row in list for descending data/last row in list for ascending data
    is correct. Further development may be able to find a workaround to this limitation."""
    # First sort the list by required dictionary key in the specified order
    sorted_list = sorted(l, key=lambda team: int(team[dict_key]), reverse=descending)
    original_list = l
    bad_dicts = []
    # If it's a descending list, remove every element from the beginning until the matching first item is reached
    if descending:
        while original_list[0][dict_key] != sorted_list[0][dict_key]:
            sorted_list.pop(0)
    # If it's an ascending list, remove every element from the end until the matching last item is reached
    else:
        while original_list[-1][dict_key] != sorted_list[-1][dict_key]:
            sorted_list.pop(-1)
    # Find which elements were removed from the original list and add the element index to the output list
    for original_dict in original_list:
        exists = False
        for sorted_dict in sorted_list:
            if original_dict[dict_key] == sorted_dict[dict_key]:
                exists = True
                break
        if not exists:
            bad_dicts.append(original_dict)
    # Return the output list of indices from the original list that contain incorrect values
    return bad_dicts


def remove_inconsecutive_in_list(l, dict_key, descending=False):
    """Remove any dictionaries in a list that aren't in ascending/descending order."""
    """As the application of this program favours correct data over complete data, it is a
    lot more worthwhile to remove incorrect data than keep it for increasing quantity.

    In future development, an attempt to correct the data can be made, rather than completely
    removing all incorrect data. The removal of data can be used instead as a last resort."""
    # Use the function above to find the indices of elements that should be removed
    remove_list = find_inconsecutive_in_dict_list(l, dict_key, descending)
    out_list = l
    # Remove any indicies from the original list
    for i in remove_list:
        out_list.remove(i)
    # Return the altered list
    return out_list


def get_name_corrections_regex(team_list):
    """Correct the team list using RegEx from file."""
    # Read from the csv file for name corrections in regex format and add to the list
    nameCorrectionRegex = []
    with open(nameCorrectionRegexPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter='¦')
        for row in reader:
            nameCorrectionRegex.append((row["Pattern"], row["Correct name"]))
    # Correct team names based on the regex of names submitted by the user
    for line in team_list:
        for pattern, value in nameCorrectionRegex:
            if re.search(pattern, line["name"]):
                line["name"] = value
    # Return the list of teams corrected
    return team_list


def get_name_corrections_contains(team_list):
    """Correct the team list using substring containment from file."""
    # Read from the csv file for name corrections that contain a keyword and add to the dictionary
    nameCorrectionContains = {}
    with open(nameCorrectionContainsPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            nameCorrectionContains[row["Identified name"]] = row["Correct name"]
    # Correct team names based on user submitted preferences of names containing keywords
    for line in team_list:
        for key in nameCorrectionContains:
            if key in line["name"]:
                line["name"] = nameCorrectionContains[key]
    # Return the list of teams corrected
    return team_list


def get_name_corrections_exact(team_list):
    """Correct the team list using exact matching strings from file."""
    # Read from the csv file for name corrections and add to the dictionary
    nameCorrection = {}
    with open(nameCorrectionPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            nameCorrection[row["Identified name"]] = row["Correct name"]
    # Correct team names based on user submitted preferences
    for line in team_list:
        if line["name"] in nameCorrection:
            line["name"] = nameCorrection[line["name"]]
    # Return the list of teams corrected
    return team_list


def get_team_end_times_from_file():
    """Get the data from the spreadsheet into a list of dictionaries and return the list."""
    teamEndTimes = []
    with open(teamEndTimesPath, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            teamEndTimes.append({})
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


def update_spreadsheet(team_list, teamEndTimes, timestamp):
    """Update the spreadsheet list with the new SS data."""
    # First, use the previous timestamp saved in "timestamp checked" to update the prior timestamp
    for team in teamEndTimes:
        team["timestamp prior"] = team["timestamp checked"]

    # Add the new team screenshot data to the spreadsheet
    for team in team_list:
        # If the team being examined isn't already in the spreadsheet,
        # add it with placeholders as "N/A" for data unavailable until the team's cups changes next
        if not any(d["name"] == team["name"] for d in teamEndTimes):
            teamEndTimes.append({"position": team["position"],
                                 "name": team["name"],
                                 "cups": team["cups"],
                                 "match against": "N/A",
                                 "cup change": "N/A",
                                 "timestamp prior": "N/A",
                                 "timestamp checked": timestamp,
                                 "timestamp changed": "N/A"})
        # Otherwise, the team already exists in the spreadsheet, so find the team with the same name,
        # update its position number and timestamp checked, then check if there was a total cups change,
        # which means it just finished a match.
        else:
            for savedTeam in teamEndTimes:
                if savedTeam["name"] == team["name"]:
                    savedTeam["position"] = team["position"]
                    savedTeam["timestamp checked"] = timestamp
                    if savedTeam["cups"] != team["cups"]:
                        # Work out the change in cups and update that field for the team's record
                        savedTeam["cup change"] = str(int(team["cups"]) - int(savedTeam["cups"]))
                        # Update the cups value to the new, changed cups value
                        savedTeam["cups"] = team["cups"]
                        # Save the new timestamp to the "timestamp changed" field
                        savedTeam["timestamp changed"] = timestamp
    # (Part of adding new team screenshot to spreadsheet above)
    # Deal with adding the data about which teams this team may have played against to change its total cups this way
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
            # Look through the data to find a team that had the same timestamp, that is also not the same team being examined
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

    # Return the final updated teamEndTimes file as a list
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


def get_datetime_from_string(input_string):
    """Get a datetime object from the user input string and return feedback string if invalid string."""
    # Split the string by space to get each part of the command
    split = input_string.split(' ')
    # Placeholder string used in case datetime doesn't parse
    out_string = "Success"
    # Set the datetime object to false by default until a datetime value is found
    dt = False
    # Get the datetime part of the string
    if len(split) > 1:
        # Get the timezone part of the string if it exists
        if len(split) > 2:
            # Attempt to get the timezone from the part of the string 
            tz = get_official_tz(split[2])
            # If the timezone is correct, try to parse the timestamp part
            if tz:
                dt = try_parsing_date(split[1], tz)
                if not dt:
                    # Set the output string to an informative error for the user
                    out_string = "Invalid timestamp format in command."
            else:
                out_string = "Invalid timezone in command."
        # If timezone doesn't exist, use UTC timezone with the timestamp string
        else:
            dt = try_parsing_date(split[1], pytz.timezone("UTC"))
            # Set the output string to an informative error for the user
            if not dt:
                out_string = "Invalid timestamp format in command."
    # Set the output string to an informative error for the user
    else:
        out_string = "No timestamp included in command."
    
    return out_string, dt


@client.event
async def on_ready():
    """Check that connection to the Discord server has been established."""
    print(f'{client.user.name} has connected to Discord!')


@client.event
async def on_message(message):
    """Retreives the image from Discord."""
    # Make sure the bot isn't replying to itself
    if message.author == client.user:
        return
    # !end command initiates the bot to find screenshots uploaded and process them
    elif message.content.startswith("!end"):
        found_start = False
        # Attempt to get a datetime object from the end command, otherwise it will be taken from !start
        out_error, dt = get_datetime_from_string(message.content)
        # Get the channel history to find uploaded images and !start command
        history = await message.channel.history().flatten()
        get_SS_from_msg_before = 0
        # Iterate over every message in history to find a message beginning with !start
        for i, msg in enumerate(history):
            # To prevent old images from being used, stop when the previous
            # !end command is reached unless it's the current message
            if msg.content.startswith("!end") and msg != message:
                break
            # When a start command is found, indicate this, save the message number
            # to know where to stop using the list of messages and try to get a datetime
            # object from the message if not already found.
            elif msg.content.startswith("!start"):
                found_start = True
                get_SS_from_msg_before = i
                if not dt:
                    out_error, dt = get_datetime_from_string(msg.content)
                break
        # Set the output error message if the !start command couldn't be found
        if not found_start:
            out_error = "Could not find start of screenshots! Please make sure to use !start before uploading any screenshots."
        # !start found and datetime object parsed sucessfully
        if found_start and dt:
            # Trim the message history to get only until !start command was found
            history = history[:get_SS_from_msg_before + 1]
            # Reverse the history to get screenshots in order of upload
            history.reverse()
            imageNum = 0
            img_list = []
            # Loop over every message in the history of interest
            for msg in history:
                # Get the images from the attachment URL
                async with aiohttp.ClientSession() as session:
                    # Loop over every image in the message attachments
                    for attachment in msg.attachments:
                        # Increase the counter for the image number (useful for error analysis)
                        imageNum += 1
                        # Download the image from URL of the attachment
                        async with session.get(attachment.url) as response:
                            # A successful download produces a status code of 200
                            if response.status != 200:
                                # Use a placeholder for the image in the list since the actual one can't be downloaded
                                img_list.append(False)
                                # Let the user know the message can't be downloaded
                                await message.channel.send(f"Could not download image {imageNum}.")
                            # Convert the image into an OpenCV image
                            data = io.BytesIO(await response.read())
                            img = cv2.imdecode(np.frombuffer(data.read(), np.uint8), 1)
                            # Add the image to the img_list
                            img_list.append(img)
            
            if len(img_list) > 0:
                # Get one long list by taking data from each image to construct the dictionary table of teams
                team_list = []
                # Start with an iterator value of 1 for easier error readability and loop through each image
                for i, img in enumerate(img_list, 1):
                    # Expect an error out of each image, so use exception handling
                    try:
                        # If all goes well, add the team info to the main team list
                        l = await SS_extract_text(img)
                        # Make sure only correct data passes to the final list
                        # This is done on each SS individually, rather than the whole list of data to improve accuracy,
                        # as in position numbers having an extra number in one of the rows wouldn't place it at the end
                        # of the list but somewhere in the middle, making it impossible to find with the method being used.
                        l = remove_inconsecutive_in_list(l, "position", descending=False)
                        l = remove_inconsecutive_in_list(l, "cups", descending=True)
                        team_list.append(l)
                    except Exception as e:
                        # If an individual screenshot had any issues, this is shown to the user
                        if e == "Uneven rows were found.":
                            out_string = f"Problem with screenhot {i}: {e}"
                            embed_block = discord.Embed(description=out_string, color=embed_failure_color)
                            await message.channel.send(embed=embed_block)
                        else:
                            out_string = f"Problem with screenhot {i}: Error reading screenshot"
                            embed_block = discord.Embed(description=out_string, color=embed_failure_color)
                            await message.channel.send(embed=embed_block)
                # Flatten the team list so that each team entry is a separate item in one list
                team_list = [item for sublist in team_list for item in sublist]
                
                # Correct team names using RegEx
                team_list = get_name_corrections_regex(team_list)
                # Correct team names using substring containment
                team_list = get_name_corrections_contains(team_list)
                # Correct team names using exact matching strings
                team_list = get_name_corrections_exact(team_list)
                
                # There may be duplicate team names from the resulting screenshots,
                # so just add an extra number to the end to fix them
                team_list = fixDupTeamNames(team_list)
                
                # Let the user know which position numbers were successfully added to the spreadsheet
                position_nums = []
                for team in team_list:
                    position_nums.append(int(team["position"]))
                await message.channel.send(consectutive_group_to_string(position_nums))
                
                # Get the data from the spreadsheet into a separate list of dictionaries
                teamEndTimes = get_team_end_times_from_file()
                
                # Get the datetime object as a UTC timestamp
                dt_utc = dt.astimezone(pytz.timezone("UTC"))
                timestamp_string = dt_utc.strftime(datetime_format)
                
                # Update the spreadsheet list using the new SS data
                teamEndTimes = update_spreadsheet(team_list, teamEndTimes, timestamp_string)
                
                # Sort the spreadsheet data by position number
                teamEndTimes.sort(key=lambda team: int(team["position"]))
                
                # Rewrite the spreadsheet file with the new updated data
                write_new_spreadsheet_data(teamEndTimes)
            # Since no images were uploaded if there aren't any in the list, let the user know
            else:
                out_string = "No screenshot images were uploaded."
                embed_block = discord.Embed(description=out_string, color=embed_nodata_color)
                await message.channel.send(embed=embed_block)
        # Let the user know what went wrong with their upload command
        else:
            embed_block = discord.Embed(description=out_error, color=embed_failure_color)
            await message.channel.send(embed=embed_block)


# Run the bot using the Discord client and bot token
client.run(TOKEN)
