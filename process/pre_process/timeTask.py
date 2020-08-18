# ---------------------------------------------------------------------------
# Purpose: Timer function to use in other scripts
# Author:  Carl Higgs
# Date:    2016 11 01
#
# Status: development
# ---------------------------------------------------------------------------



def timeTask(task="no task defined",script="no script specified"):
  from datetime import datetime
  import logging
  formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
  

  LOG_FILENAME = os.path.join(os.path.dir(script),script+'.log')
  
  
  print("Started: "+str(datetime.now()))
  print("Running: "+script)
  print("Purpose: "+task)
  import time
  import os
  start = time.time()
  try:
    # naive timer (ideally timing should be tested over iterations)
    os.system(script)
    taskEnd = time.time()
    text_file = open("Output.txt", "w")
    print("Finished: "+str(datetime.now()))
    print("Processing complete (Task: {}); duration: {:04.2f} minutes".format(task,(taskEnd - start)/60))
  except:
    taskEnd = time.time()
    print("Finished: "+str(datetime.now()))
    print("Script run in timer function failed at {}.".format(task,(taskEnd - start)/60))
    raise

    
def logger(string = "message"):
  # create logger
  logger = logging.getLogger()
  logger.setLevel(logging.DEBUG)
  # create console handler and set level to debug
  ch = logging.StreamHandler()
  ch.setLevel(logging.DEBUG)
  # create formatter
  formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
  # add formatter to ch
  ch.setFormatter(formatter)
  # add ch to logger
  logger.addHandler(ch)
  
  # "application" code
  logger.debug("debug message")
  logger.info("info message")
  logger.warn("warn message")
  logger.error("error message")
  logger.critical("critical message")

# Write the output to a text file
text_file.write("OID = %s; count = %s" % (max(data, key = data.get), data[max(data, key = data.get)]))
text_file.close()