


const{ app,BrowserWindow,Menu, ipcMain,screen}=require('electron');
const path=require('path');

const {spawn}=require("child_process");

let pyServer;


let mainWindow;
let settingsWindow=null;
let panelMode=false;


function startPython(script){   
    pyServer=spawn("python",[script]);
    pyServer.stdout.on("data", (data) => {
        console.log("PYTHON:", data.toString());
    });

    pyServer.stderr.on("data", (data) => {
        console.error("PYTHON ERROR:", data.toString());
    });

}




function createWindow(){
    //Menu.setApplicationMenu(null)
    //create the main window on start up
    mainWindow=new BrowserWindow({
        width:800,
        height:600,
        frame:true,
        webPreferences:{
            //preload done for settings, wont work without it for some reason
            //preload:path.join(__dirname,'preload.js'),
            nodeIntegration:true,
            contextIsolation:false
        }
        
    });

    //loads the main html
    mainWindow.loadFile('public/index.html');

}




//for the chatbot panel
//NOT USED NOW
ipcMain.handle('toggle-panel',()=>{
    const {width,height}=screen.getPrimaryDisplay().workArea;

    if(!panelMode){
        mainWindow.setBounds({
            x:0,
            y:0,
            width:400,
            height:height
        });
        mainWindow.setAlwaysOnTop(true);
    }else{
        mainWindow.setBounds({
            x:0,
            y:0,
            width:1000,
            height:1000
        });
        mainWindow.setAlwaysOnTop(false);
    }
    panelMode=!panelMode;
});



app.whenReady().then(()=>{
    startPython("Python_files/WebSocket_broadcast.py");
    startPython("Python_files/EOG_control.py");
    startPython("Python_files/main.py");   
    createWindow();

    app.on('activate', function(){
        if(BrowserWindow.getAllWindows().length===0) createWindow();

    });
});

app.on('window-all-closed',()=>{
    if(process.platform!=='darwin'){
        app.quit();
    }
});



