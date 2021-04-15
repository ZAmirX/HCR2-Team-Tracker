# HCR2-Team-Tracker
OCR Discord bot for tracking top teams in HCR2

## INSTRUCTIONS


### Reader bot

<ins>Quality of screenshots</ins><br>
Before posting any screenshots, it is important to first make sure there aren’t any obstructions that affect the quality of the image shown. An example of a bad quality screenshots is shown below:

You can see the top left is VIP chest is obstructing the first team’s trophies. Make sure that has been cleared away before starting to take the screenshots.
The other obstruction is at the bottom, covering the team’s name. If at all possible, please try and find a way to hide the bar from your device settings, for at least the duration of taking the screenshots.

<ins>Uploading screenshots</ins><br>
You can continue uploading the same times as before, except the way is slightly different. Always start with !start command before adding any images. Then upload screens for all 108 teams and at the end, use the !end command. The time needs to be put after at least one of the two commands, and optionally followed by the time zone you are in, otherwise UTC time zone is used. So, the usage is:<br>
!start 2021-04-14T20:00 Europe/London<br>
(Year-Month-DayCapitalTHour:Minute)<br>
OR<br>
!start 20:00 Europe/London<br>
(bearing in mind that not specifying the date will assume it’s the same day, so make sure to use the full date and time format if it’s past midnight in your time zone)

Alternatively, you may skip putting the time after the start command completely, so long as you put it with the !end command. So, it would look like this:<br>
!end 2021-04-14T20:00 Europe/London

You may even put the time for both !start and !end commands, just bear in mind that the time after the !end command overwrites the time after the !start command, but it must be present in at least one or the other.<br>
If you make a mistake with the !end command, just delete the !end message and send it again correctly, as the screenshots aren’t analysed until the !end command is sent correctly. You’ll know that the images were sent successfully when the bot replies after some time saying something like:<br>
Successfully added data on teams in positions 1-108.

<ins>Time zones</ins><br>
Time zones that are used for adding screenshot data rely on IANA time zone database. The full list can be found here:<br> https://en.wikipedia.org/wiki/List_of_tz_database_time_zones<br>
However, this has been simplified so that it’s easier by adding shortcuts in the Query channel. So, for example, Europe/London has been shortened to UK by using these shortcuts. By using the shortcut, the !end command could look like this shortened:<br>
!end 20:00 UK


### Query bot

<ins>Time zones</ins><br>
Time zones that are used for checking teams rely on IANA time zone database. The full list can be found here: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
However, this has been simplified so that it’s easier by adding shortcuts in the Query channel. So, for example, Europe/London has been shortened to UK by using these shortcuts. By using the shortcut, the !time command could look like this shortened:<br>
!time 20:00 UK

<ins>Commands</ins><br>
**team**<br>
Search for top teams by name to find when they last ended.<br>
Usage: !team \`team name\` timezone<br>
timezone is optional, but when not used, UTC time is used instead. Team name needs to be wrapped in backticks (\`) when using space in between one name. It should look like this for example:<br>
!team `Redd|IT` Europe/London

**time**<br>
Search for top teams supposedly ending at a specified time, assuming all teams start another match immediately after ending the previous one. The search range is +/- 1 hour.<br>
Usage: !time timestamp timezone<br>
timezone is optional, but when not used, UTC time is used instead. timestamp has to be in either format Year-Month-DayTHour:Minute (e.g. 2021-04-14T20:00) or Hour:Minute (e.g. 20:00). If the time only format is used rather than date & time, it will be assumed you are searching on the same day during your specified time zone.

**add_tz**<br>
Add a new timezone shortcut that uses an official time zone from the TZ database. This would make it easier to specify your time zone in future queries and screenshot uploads.<br>
Usage: !add_tz shortcut timezone<br>
Where shortcut is the new shortcut you want to add and timezone is the official time zone from the IANA database (see the link to the list above). For example: !add_tz UK Europe/London

**correct**<br>
Add a new team name correction to the spreadsheet so that the correct team can be tracked. Corrects any instance of the specified correction based on exact name match. This is the safest correction that can be made without affecting other team names.<br>
Usage: !correct \`wrong team name\` \`correct team name\`<br>
Backticks need to be used if there are spaces between a single team name.

**correct_contains**<br>
Add a new team name correction to the spreadsheet so that the correct team can be tracked. Corrects any instance of the specified correction based on any name containing the wrong team name. Be careful when using this method as a correction to one team may affect another. For example, making sure occurrence of ITALIA is left as only ITALIA would affect and change STORMO ITALIA to only ITALIA as well.<br>
Usage: !correct_contains \`wrong team name\` \`correct team name\`<br>
Backticks need to be used if there are spaces between a single team name.

**correct_regex**<br>
Add a new team name correction to the spreadsheet so that the correct team can be tracked. Corrects any instance of a Regular Expression pattern to the new team name. This is only recommended if you know what you’re doing. You can check the RegEx rules here: https://www.rexegg.com/regex-quickstart.html and test your pattern here: https://regex101.com/ <br>
Usage: !correct_regex \`Pattern\` \`correct team name\`<br>
Backticks need to be used if there are spaces between a single pattern/team name.

**get_spreadsheet**<br>
Send the current state of the spreadsheet for debugging use. You can use this to check if there are any incorrect team names in the spreadsheet that need to be corrected.
