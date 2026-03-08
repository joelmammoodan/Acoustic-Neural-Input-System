


const{ app,BrowserWindow,Menu, ipcMain,screen}=require('electron');
const path=require('path');


let mainWindow;
let settingsWindow=null;
let panelMode=false;


function createWindow(){
    //Menu.setApplicationMenu(null)
    //create the main window on start up
    mainWindow=new BrowserWindow({
        width:800,
        height:600,
        frame:true,
        webPreferences:{
            //preload done for settings, wont work without it for some reason
            preload:path.join(__dirname,'preload.js'),
            nodeIntegration:false,
            contextIsolation:true
        }
        
    });

    //loads the main html
    mainWindow.loadFile('public/index.html');

}

ipcMain.handle('open-settings',()=>{
    //logic for closing and opening the windows
    if(settingsWindow && !settingsWindow.isDestroyed()){
        settingsWindow.show();
        settingsWindow.focus()        
        return;
    }
    console.log(__dirname)
    //new window for settings
    settingsWindow=new BrowserWindow({
        width:500,
        height:400,
        parent:mainWindow,
        modal:false,
        title:"Settings"
    });

    settingsWindow.loadFile('public/settings.html')
})


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

