import pyautogui
import time
import keyboard

offsetY=10
offsetY=10

posX,posY=pyautogui.position()


def move(offset_func,click_threshold):
    
    pyautogui.FAILSAFE=True
    prevX,prevY=pyautogui.position()
    startTime=time.perf_counter()
    

    while (True):
        posX,posY=pyautogui.position()
        currTime=time.perf_counter()
        print(currTime-startTime)
        #print(posX,posY)
        offsetX,offsetY=offset_func()
        
        pyautogui.moveRel(offsetX,offsetY,_pause=False)
    
        
        if((posX-prevX==0) and (posY-prevY==0)):
            if((currTime-startTime)>=click_threshold):
                pyautogui.click()
                print("Mouse Clicked")
                startTime=currTime
        else:
           startTime=currTime
        prevX,prevY=posX,posY
        time.sleep(1/120)

def offset_func():
    if(keyboard.is_pressed('w')):
        return (0,-1)
    elif(keyboard.is_pressed('a')):
        return(-1,0)
    elif(keyboard.is_pressed('s')):
        return(0,1)
    elif(keyboard.is_pressed('d')):
        return(1,0)
    else:
        return(0,0)
        


    
    



move(offset_func,5)