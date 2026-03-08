const { contextBridge , ipcRenderer}=require("electron");

console.log("Preload is loading...")

contextBridge.exposeInMainWorld("api",{
    openSettings:() => ipcRenderer.invoke("open-settings")
});