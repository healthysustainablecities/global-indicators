# Script:  progressor.py
# Purpose: a progress percent timer function
#           -- place in a loop
#           -- initialises with numerator of zero
#           -- completes with numerator of 100% or greater
#           -- suggests a problem may have occurred if 
#              numerator is greater than 100%
#           -- optionally provide a start time to tally HMS
#              and provide ETA based on linear completion rate.
#               -- define 'startClock = time.time()' outside of loop
#                  and provide startClock as start parameter
#           -- optionally define a task name to be printed
# Author:  Carl Higgs
# Date:    29/12/2016


def progressor(num = 0, denom = 100, start = None, task = ''):
  import time
  
  if (num < 0):
    print("Possible error: numerator is negative - is this right?")
    
  if num >= 0:
    pct = (float(num)/denom)*100
    HMS = ''
    eta  = ''
    mult = 9 + len(task)
    if type(start) in (int,float):
      secs     = (time.time()-start)
      etaT     = start+((secs/(num+0.001))*denom)
      HMS     = ' {} '.format(time.strftime("%H:%M:%S", time.gmtime(secs)))
      eta      = ' (ETA: {}) '.format(time.strftime("%Y%m%d_%H%M",time.localtime(etaT)))
      mult += len(HMS)+len(eta)
    if num == 0:
      todayhour = time.strftime("%Y%m%d_%H%M")
      print("Start: {} ".format(todayhour))
      print("{:5.2f}% {}{}".format(0,task,' '*(mult-len(task)-9))),
    print("\b"*mult),
    print("{:5.2f}%{}{} {}".format(pct,HMS,eta,task)),
    if num >= denom:
      todayhour = time.strftime("%Y%m%d_%H%M")
      print("\nComplete: {}".format(todayhour))
      if num > denom:
        print("\nPossible error: numerator is greater than denominator.  Is this right?")
 
if __name__ == '__main__':  
  import time
  
  print("Example usage of progressor function")
  print('''
    progressor(num,denom)
  ''')
  
  denom  = 3
  start = time.time()
  for num in range(0,denom+1):
    progressor(num,denom)
    time.sleep(1)
  print("Task duration = {:9.2f}".format((time.time()-start)/60))
  
  
  print('''
    progressor(num,denom,task = taskName)
  ''')
  denom  = 3
  start = time.time()
  taskName = 'Display task progress with task name'
  for num in range(0,denom+1):
    progressor(num,denom,task = taskName)
    time.sleep(1)
  print("Task duration = {:9.2f}".format((time.time()-start)/60))
  
  print('''
    progressor(num,denom,start,taskName)
  ''')
  denom  = 12
  start = time.time()
  taskName = 'Display task progress with task name'
  for num in range(0,denom+1):
    progressor(num,denom,start,taskName)
    time.sleep(1)
  print("Task duration = {:9.2f} minutes".format((time.time()-start)/60))
