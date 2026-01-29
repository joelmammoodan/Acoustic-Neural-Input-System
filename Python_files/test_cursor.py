import pyautogui

'''screen=pyautogui.size()
print(screen)


#move mouse relative to pointer
pyautogui.moveRel(offsetX,offsetY,duration=time);

#for screen size
screenWidth, screenHeight = pyautogui.size()

#to egt cursor position
currentMouseX, currentMouseY = pyautogui.position()

pyautogui.moveTo(100, 150) # Move the mouse to XY coordinates.

pyautogui.click()          # Click the mouse.
pyautogui.click(100, 200)  # Move the mouse to XY coordinates and click it.
pyautogui.click('button.png') # Find where button.png appears on the screen and click it.
pyautogui.doubleClick()     # Double click the mouse.
pyautogui.press('esc')
pyautogui.alert('This is the message to display.')
'''



def spiral_circle():
    width,height=pyautogui.size()
    dist=400
    pyautogui.moveTo((width/2)+300,(height/2)-100)
    while(dist>0):
        pyautogui.moveRel(dist,0)
        pyautogui.click()
        pyautogui.moveRel(0,dist)
        pyautogui.click()
        dist-=1
        pyautogui.moveRel(-dist,0)
        pyautogui.click()
        pyautogui.moveRel(0,-dist)
        pyautogui.click()
        dist-=1


spiral_circle()