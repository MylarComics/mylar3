# This script was initially based from Manders2600 Script with the use of the awesome ComicTagger.
# Modified, so Mylar just can pass in relevant information instead of querying CV for it to do it's magic.


import os, errno
import sys
import re
import glob
import shlex
import platform
import shutil
import time
import zipfile
import subprocess
from urllib.parse import urlsplit, urlunsplit
import mylar

from mylar import logger, notifiers


def run(dirName, nzbName=None, issueid=None, comversion=None, manual=None, filename=None, module=None, manualmeta=False, readingorder=None, agerating=None):
    if module is None:
        module = ''
    module += '[META-TAGGER]'

    logger.fdebug(module + ' dirName:' + dirName)

    # Use the console script installed with the pinned upstream dependency.
    # The fallback covers virtual environments whose bin directory is not on PATH.
    comictagger_cmd = shutil.which('comictagger')
    if comictagger_cmd is None:
        candidate = os.path.join(os.path.dirname(sys.executable), 'comictagger')
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            comictagger_cmd = candidate
    if comictagger_cmd is None:
        logger.warn(module + '[WARNING] ComicTagger is not installed. Install requirements.txt and retry metatagging.')
        return 'fail'
    logger.fdebug('ComicTagger executable: ' + comictagger_cmd)

    logger.fdebug(module + ' Filename is : ' + filename)

    filepath = filename
    og_filepath = filepath
    try:
        filename = os.path.split(filename)[1]   # just the filename itself
    except:
        logger.warn('Unable to detect filename within directory - I am aborting the tagging. You best check things out.')
        sendnotify("Error - Unable to detect filename within directory. Tagging aborted.", filename, module)
        return "fail"

    #make use of temporary file location in order to post-process this to ensure that things don't get hammered when converting
    new_filepath = None
    new_folder = None
    try:
        import tempfile
        logger.fdebug('Filepath: %s' %filepath)
        logger.fdebug('Filename: %s' %filename)
        new_folder = tempfile.mkdtemp(prefix='mylar_', dir=mylar.CONFIG.CACHE_DIR) #prefix, suffix, dir
        os.chmod(new_folder, 0o777)
        logger.fdebug('New_Folder: %s' % new_folder)
        new_filepath = os.path.join(new_folder, filename)
        logger.fdebug('New_Filepath: %s' % new_filepath)
        if mylar.CONFIG.FILE_OPTS == 'copy' and manualmeta == False:
            shutil.copy(filepath, new_filepath)
        else:
            shutil.copy(filepath, new_filepath)
        filepath = new_filepath
    except Exception as e:
        logger.warn('%s Unexpected Error: %s [%s]' % (module, sys.exc_info()[0], e))
        logger.warn(module + ' Unable to create temporary directory to perform meta-tagging. Processing without metatagging.')
        sendnotify("Error - Unable to create temporary directory to perform meta-tagging. Processing without metatagging.", filename, module)
        tidyup(og_filepath, new_filepath, new_folder, manualmeta)
        return "fail"

    ## Sets up other directories ##
    scriptname = os.path.basename(sys.argv[0])
    downloadpath = os.path.abspath(dirName)
    sabnzbdscriptpath = os.path.dirname(sys.argv[0])
    comicpath = new_folder

    logger.fdebug(module + ' Paths / Locations:')
    logger.fdebug(module + ' scriptname : ' + scriptname)
    logger.fdebug(module + ' downloadpath : ' + downloadpath)
    logger.fdebug(module + ' sabnzbdscriptpath : ' + sabnzbdscriptpath)
    logger.fdebug(module + ' comicpath : ' + comicpath)
    logger.fdebug(module + ' Running the ComicTagger Add-on for Mylar')


    ##set up default comictagger options here.
    #used for cbr - to - cbz conversion
    #depending on copy/move - eitehr we retain the rar or we don't.
    cbr2cbzoptions = ["--config", mylar.CONFIG.CT_SETTINGSPATH, "-e"]
    if mylar.CONFIG.FILE_OPTS == 'move':
        cbr2cbzoptions.append("--delete-rar")

    tagoptions = ["-s"]

    cvers = "volume="
    if mylar.CONFIG.CMTAG_VOLUME:
        if mylar.CONFIG.CMTAG_START_YEAR_AS_VOLUME:
            pass
            # comversion is already converted - just leaving this here so we know
        else:
            if mylar.CONFIG.SETDEFAULTVOLUME:
                if any([comversion is None, comversion == '', comversion == 'None']):
                    comversion = '1'
                comversion = re.sub('[^0-9]', '', comversion).strip()
            else:
                if any([comversion is None, comversion == '', comversion == 'None']):
                    comversion = None
                else:
                    comversion = re.sub('[^0-9]', '', comversion).strip()
        if comversion is not None:
            cvers = 'volume=%s' % comversion

    storyarc = ''
    if isinstance(readingorder, list):
        storyarc = re.sub(r',', '^,', ','.join(osq[0] for osq in readingorder).strip())
    maturity_rating = agerating if all([agerating is not None, agerating != 'None']) else ''
    tagoptions.extend(["-m", 'volume=%s, story_arc=%s, maturity_rating=%s' % (
        cvers.replace('volume=', '', 1), storyarc, maturity_rating,
    )])

    try:
        # ComicTagger 1.5.5 exits 1 after printing --version; its banner is
        # the successful health-check signal instead of the return code.
        ct_process = subprocess.run(
            [comictagger_cmd, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        ct_check = ct_process.stdout
    except OSError:
        logger.warn(module + '[WARNING] Make sure that you are using the comictagger included with Mylar.')
        tidyup(filepath, new_filepath, new_folder, manualmeta)
        return "fail"

    logger.info('ct_check: %s' % ct_check)
    if b'ComicTagger ' not in ct_check:
        logger.warn(module + '[WARNING] Unable to start the bundled ComicTagger.')
        tidyup(filepath, new_filepath, new_folder, manualmeta)
        return "fail"

    if any([mylar.CONFIG.COMICVINE_API == 'None', mylar.CONFIG.COMICVINE_API is None]):
        logger.fdebug('%s No personal ComicVine API key supplied. Take your chances.' % module)
    else:
        logger.fdebug('%s Using the personal ComicVine API key supplied via Mylar.' % module)
        tagoptions.extend(["--cv-api-key", mylar.CONFIG.COMICVINE_API, "--config", mylar.CONFIG.CT_SETTINGSPATH])
        cv_api_url = getattr(mylar.CONFIG, "COMICVINE_URL", None)
        if cv_api_url:
            cv_api_url = cv_api_url.strip().rstrip("/")
        if not cv_api_url:
            cv_api_url = "https://comicvine.gamespot.com/api"

        # The configured value is an API base URL.  A bare host (for example
        # https://fv.titor.dev) needs the standard /api path used upstream.
        parsed_url = urlsplit(cv_api_url)
        if parsed_url.path in ('', '/'):
            cv_api_url = urlunsplit((
                parsed_url.scheme,
                parsed_url.netloc,
                '/api',
                parsed_url.query,
                parsed_url.fragment,
            ))
        tagoptions.extend(["--cv-url", cv_api_url])

    i = 1
    tagcnt = 0

    if mylar.CONFIG.CBR2CBZ_ONLY:
        logger.fdebug(module + ' CBR2CBZ Conversion only.')
    else:
        if mylar.CONFIG.CT_TAG_CR:
            tagcnt = 1
            logger.fdebug(module + ' CR Tagging enabled.')

        if mylar.CONFIG.CT_TAG_CBL:
            if not mylar.CONFIG.CT_TAG_CR: i = 2  #set the tag to start at cbl and end without doing another tagging.
            tagcnt = 2
            logger.fdebug(module + ' CBL Tagging enabled.')

    if tagcnt == 0 and not mylar.CONFIG.CBR2CBZ_ONLY:
        logger.warn(module + ' You have metatagging enabled, but you have not selected the type(s) of metadata to write. Please fix and re-run manually')
        tidyup(filepath, new_filepath, new_folder, manualmeta)
        return "fail"

    #if it's a cbz file - check if no-overwrite existing tags is enabled / disabled in config.
    if filename.endswith('.cbz'):
        if mylar.CONFIG.CT_CBZ_OVERWRITE:
            logger.fdebug(module + ' Will modify existing tag blocks even if it exists.')
        else:
            logger.fdebug(module + ' Will NOT modify existing tag blocks even if they exist already.')
            tagoptions.extend(["--nooverwrite"])

    if issueid is None:
        tagoptions.extend(["-f", "-o"])
    else:
        tagoptions.extend(["-o", "--id", issueid])

    original_tagoptions = tagoptions
    og_tagtype = None
    initial_ctrun = True

    while (i <= tagcnt):
        if initial_ctrun:
            f_tagoptions = cbr2cbzoptions
            f_tagoptions.extend([filepath])
        else:
            if i == 1:
                tagtype = 'cr'  # CR meta-tagging cycle.
                tagdisp = 'ComicRack tagging'
            elif i == 2:
                tagtype = 'cbl'  # Cbl meta-tagging cycle
                tagdisp = 'Comicbooklover tagging'

            f_tagoptions = original_tagoptions

            if og_tagtype is not None:
                for index, item in enumerate(f_tagoptions):
                    if item == og_tagtype:
                        f_tagoptions[index] = tagtype
            else:
                f_tagoptions.extend(["--type", tagtype, filepath])

            og_tagtype = tagtype

            logger.info(module + ' ' + tagdisp + ' meta-tagging processing started.')

        currentScriptName = [comictagger_cmd]
        script_cmd = currentScriptName + f_tagoptions

        if initial_ctrun:
            logger.fdebug('%s Enabling ComicTagger script with options: %s' % (module, f_tagoptions))
            script_cmdlog = script_cmd

        else:
            logger.fdebug('%s Enabling ComicTagger script with options: %s' %(module, re.sub(f_tagoptions[f_tagoptions.index(mylar.CONFIG.COMICVINE_API)], 'REDACTED', str(f_tagoptions))))
            # generate a safe command line string to execute the script and provide all the parameters
            script_cmdlog = re.sub(f_tagoptions[f_tagoptions.index(mylar.CONFIG.COMICVINE_API)], 'REDACTED', str(script_cmd))

        logger.fdebug(module + ' Executing command: ' +str(script_cmdlog))
        logger.fdebug(module + ' Absolute path to script: ' +script_cmd[0])
        try:
            # use subprocess to run the command and capture output
            p = subprocess.Popen(script_cmd, stdout=subprocess.PIPE, text=True, stderr=subprocess.STDOUT)
            out, err = p.communicate()
            #logger.info(out)
            #logger.info(err)
            #if out is not None:
            #    out = out.decode('utf-8')
            if all([err is not None, err != '']):
                logger.warn('[ERROR RETURNED FROM COMIC-TAGGER] %s' % (err,))
            #    err = err.decode('utf-8')
            if initial_ctrun and 'exported successfully' in out:
                logger.fdebug('%s[COMIC-TAGGER] : %s' % (module, out))
                #Archive exported successfully to: X-Men v4 008 (2014) (Digital) (Nahga-Empire).cbz (Original deleted)
                exported = re.search(
                    r'^(?:Archive )?exported successfully to:\s*(.+?)(?:\s+\(Original deleted\))?\s*$',
                    out,
                    re.IGNORECASE | re.MULTILINE,
                )
                if exported is None:
                    logger.warn('%s[COMIC-TAGGER] Could not determine the exported CBZ filename.' % module)
                    tidyup(og_filepath, new_filepath, new_folder, manualmeta)
                    return 'fail'
                tmpfilename = exported.group(1).strip()
                tmpf = tmpfilename
                filepath = os.path.join(comicpath, tmpf)
                if filename.lower() != tmpf.lower() and tmpf.endswith('(1).cbz'):
                    logger.fdebug('New filename [%s] is named incorrectly due to duplication during metatagging - Making sure it\'s named correctly [%s].' % (tmpf, filename))
                    tmpfilename = filename
                    filepath_new = os.path.join(comicpath, tmpfilename)
                    try:
                        os.rename(filepath, filepath_new)
                        filepath = filepath_new
                    except:
                        logger.warn('%s unable to rename file to accomodate metatagging cbz to the same filename' % module)
                if not os.path.isfile(filepath):
                    logger.fdebug('%s Trying utf-8 conversion.' % module)
                    tmpf = tmpfilename.encode('utf-8')
                    # TODO: This needs fixing to avoid it throwing errors joining string and bytes, but first we stop getting here
                    # in the first place
                    filepath = os.path.join(comicpath, tmpf)
                    if not os.path.isfile(filepath):
                        logger.fdebug('%s Trying latin-1 conversion.' % module)
                        tmpf = tmpfilename.encode('Latin-1')
                        filepath = os.path.join(comicpath, tmpf)

                logger.fdebug('%s[COMIC-TAGGER][CBR-TO-CBZ] New filename: %s' % (module, filepath))
                initial_ctrun = False
            elif initial_ctrun and any([
                'archive is not a rar' in out.lower(),
                'archive is already a zip file' in out.lower(),
            ]):
                logger.fdebug('%s Output: %s' % (module,out))
                if 'archive is already a zip file' in out.lower():
                    logger.fdebug('%s[COMIC-TAGGER] Archive is already CBZ; proceeding with tagging.' % module)
                else:
                    logger.warn('%s[COMIC-TAGGER] file is not in a RAR format: %s' % (module, filename))
                initial_ctrun = False
            elif initial_ctrun:
                initial_ctrun = False
                if any(['file is not expected size' in out, 'Failed the read' in out]):
                    logger.fdebug('%s Output: %s' % (module,out))
                    tidyup(og_filepath, new_filepath, new_folder, manualmeta)
                    return 'corrupt'
                else:
                    logger.fdebug('out: %s' % (out,))
                    logger.fdebug('filename: %s' % (filename,))
                    cbz_message = 'Failed to convert cbr to cbz - check permissions on folder %s and/or the location where Mylar is trying to tag the files from.' % mylar.CONFIG.CACHE_DIR
                    logger.warn('%s[COMIC-TAGGER][CBR-TO-CBZ]%s' % (module, cbz_message))
                    sendnotify('Error - %s' % (cbz_message), filename, module)
                    tidyup(og_filepath, new_filepath, new_folder, manualmeta)
                    return 'fail'
            elif 'Cannot find' in out:
                logger.fdebug('%s Output: %s' % (module,out))
                logger.warn('%s[COMIC-TAGGER] Unable to locate file: %s' % (module, filename))
                file_error = 'file not found||' + filename
                return file_error
            elif 'not a comic archive!' in out:
                logger.fdebug('%s Output: %s' % (module,out))
                logger.warn('%s[COMIC-TAGGER] Unable to locate file: %s' % (module, filename))
                file_error = 'file not found||%s' % filename
                return file_error
            else:
                if 'Save complete' not in out:
                    unknown_message = out
                    logger.warn('%s[COMIC-TAGGER][UNKNOWN-ERROR-DURING-METATAGGING] %s' % (module, unknown_message))
                    sendnotify('Error - %s' % (unknown_message), filename, module)
                    tidyup(og_filepath, new_filepath, new_folder, manualmeta)
                    return 'fail'
                else:
                    logger.info('%s[COMIC-TAGGER] Successfully wrote %s [%s]' % (module, tagdisp, filepath))
                i+=1
        except OSError as e:
            logger.warn('%s[COMIC-TAGGER] Unable to run comictagger with the options provided: %s' % (module, re.sub(f_tagoptions[f_tagoptions.index(mylar.CONFIG.COMICVINE_API)], 'REDACTED', str(script_cmd))))
            tidyup(filepath, new_filepath, new_folder, manualmeta)
            return "fail"
        except Exception as e:
            logger.warn('%s[COMIC-TAGGER] Error : %s' % (module, e))
            tidyup(filepath, new_filepath, new_folder, manualmeta)
            return "fail"
        if mylar.CONFIG.CBR2CBZ_ONLY and initial_ctrun == False:
            break

    return filepath


def tidyup(filepath, new_filepath, new_folder, manualmeta):
   if all([new_filepath is not None, new_folder is not None]):
        if mylar.CONFIG.FILE_OPTS == 'copy' and manualmeta == False:
            if all([os.path.exists(new_folder), os.path.isfile(filepath)]):
                shutil.rmtree(new_folder)
            elif os.path.exists(new_filepath) and not os.path.exists(filepath):
                shutil.move(new_filepath, filepath + '.BAD')
        else:
            if os.path.exists(new_filepath) and not os.path.exists(filepath):
                shutil.move(new_filepath, filepath + '.BAD')
            if all([os.path.exists(new_folder), os.path.isfile(filepath)]):
                shutil.rmtree(new_folder)

def sendnotify(message, filename, module):

    prline = filename

    prline2 = 'Mylar metatagging error: ' + message + ' File: ' + prline

    try:
        if mylar.CONFIG.PROWL_ENABLED:
            pushmessage = prline
            prowl = notifiers.PROWL()
            prowl.notify(pushmessage, "Mylar metatagging error: ", module=module)

        if mylar.CONFIG.PUSHOVER_ENABLED:
            pushover = notifiers.PUSHOVER()
            pushover.notify(prline, prline2, module=module)

        if mylar.CONFIG.BOXCAR_ENABLED:
            boxcar = notifiers.BOXCAR()
            boxcar.notify(prline=prline, prline2=prline2, module=module)

        if mylar.CONFIG.PUSHBULLET_ENABLED:
            pushbullet = notifiers.PUSHBULLET()
            pushbullet.notify(prline=prline, prline2=prline2, module=module)

        if mylar.CONFIG.TELEGRAM_ENABLED:
            telegram = notifiers.TELEGRAM()
            telegram.notify(prline2)

        if mylar.CONFIG.SLACK_ENABLED:
            slack = notifiers.SLACK()
            slack.notify("Mylar metatagging error: ", prline2, module=module)

        if mylar.CONFIG.MATTERMOST_ENABLED:
            mattermost = notifiers.MATTERMOST()
            mattermost.notify("Mylar metatagging error: ", prline2, module=module)

        if mylar.CONFIG.DISCORD_ENABLED:
            discord = notifiers.DISCORD()
            discord.notify(filename, message, module=module)

        if mylar.CONFIG.EMAIL_ENABLED and mylar.CONFIG.EMAIL_ONPOST:
            logger.info("Sending email notification")
            email = notifiers.EMAIL()
            email.notify(prline2, "Mylar metatagging error: ", module=module)

        if mylar.CONFIG.GOTIFY_ENABLED:
            gotify = notifiers.GOTIFY()
            gotify.notify("Mylar metatagging error: ", prline2, module=module)
    except Exception as e:
        logger.warn('[NOTIFICATION] Unable to send notification: %s' % e)

    return
