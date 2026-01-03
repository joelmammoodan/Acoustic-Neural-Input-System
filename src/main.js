


const{ app,BrowserWindow,Menu, ipcMain,screen}=require('electron');
const path=require('path');


let mainWindow;
let panelMode=false;


function createWindow(){
    //Menu.setApplicationMenu(null)
    mainWindow=new BrowserWindow({
        width:800,
        height:600,
        frame:true,
        webPreferences:{
            nodeIntegration:true,
            contextIsolation:false
        }
        
    });

    mainWindow.loadFile('public/index.html');

}

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

