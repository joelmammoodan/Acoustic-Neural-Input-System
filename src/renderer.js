const { ipcRenderer } = require("electron");
const fs = require("fs");

// DOM Elements
const themeBtn = document.getElementById('theme-toggle');
const icon = document.getElementById('mode');
const brain_icon=document.getElementById('brain-img');
const voice_icon=document.getElementById('voice-img');
const currentTheme = localStorage.getItem('theme');
let currentMode=localStorage.getItem('Mode');

const panelToggle = document.getElementById("panel-toggle");
const panelClosed=document.getElementById('panel-close');
const chatbotPanel = document.getElementById("chatbot-panel");
const input = document.getElementById("chat-input");
const chatBody = document.getElementById("chat-body");
const modeChangeBtn=document.getElementById('move-to-brain');
const braindiv=document.getElementById('brainmode-div');
const voicediv=document.getElementById('voicemode-div');
const modeHoverText=document.getElementById("mode-hover-text")
const settingsbtn=document.getElementById("settings-button");

let count=0;



const ws = new WebSocket("ws://localhost:8765");

ws.addEventListener('open', () => {
    console.log("WebSocket connected");
});
//const brainBtn = document.getElementById('brainBtn');
//const voiceBtn = document.getElementById('voiceBtn');

//function to extract the hex codes foro css
function cssVar(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

console.log(currentMode);

// ---------------------------
// THEME HANDLING
// ---------------------------
if(currentTheme === 'dark'){
    //set the attribute for html with dark
    document.documentElement.setAttribute('data-theme','dark');
    icon.src = '../Icons/sun.png';
    brain_icon.src='../Icons/brain_black.png';
    voice_icon.src='../Icons/voice-black.png';
    

} else {
    document.documentElement.removeAttribute('data-theme');
    icon.src = '../Icons/moon.png';
    brain_icon.src='../Icons/brain_white.png';
    voice_icon.src='../Icons/voice-white.png'; 

}

//theme button on the top bar
themeBtn.addEventListener('click', () => {
    let theme = document.documentElement.getAttribute('data-theme');

    if(theme === 'dark'){
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme','light');
        icon.src = '../Icons/moon.png';
        brain_icon.src='../Icons/brain_white.png';
        voice_icon.src='../Icons/voice-white.png'; 
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        icon.src = '../Icons/sun.png';
        brain_icon.src='../Icons/brain_black.png';
        voice_icon.src='../Icons/voice-black.png';
    }
});

//to switch any elements in voice and brain to acitve to make it hidden
function switchMode(a, b) {
    a.classList.remove("active");
    b.classList.add("active");
}


//initial checking on startup and changing accrodingly
//the mode is stored in localStorage
if(currentMode=='brain'){
    switchMode(voicediv,braindiv);
    switchMode(voice_icon,brain_icon);
    console.log('Switched to brain');
}else{
    switchMode(braindiv,voicediv);
    switchMode(brain_icon,voice_icon);
    console.log("switched to voice");
}


//to chnage the mode using the button on top bar
modeChangeBtn.addEventListener('click',()=>{
    currentMode=localStorage.getItem("Mode");
    if(currentMode=='brain'){
        switchMode(braindiv,voicediv);
        switchMode(brain_icon,voice_icon);
        currentMode='voice';
        localStorage.setItem('Mode','voice');
    }else{
        switchMode(voicediv,braindiv);
        switchMode(voice_icon,brain_icon);
        currentMode='brain';
        localStorage.setItem('Mode','brain');
    }

    console.log(currentMode);
    
   
});


// ---------------------------
// SEGMENTED BUTTONS
// ---------------------------
//brainBtn.addEventListener('click', () => {
//    brainBtn.classList.add('active');
//    voiceBtn.classList.remove('active');
//    console.log('Switched to BRAIN mode');
//    window.ipcRenderer?.send('switch-mode', 'brain');
//});

//voiceBtn.addEventListener('click', () => {
//    voiceBtn.classList.add('active');
//    brainBtn.classList.remove('active');
//    console.log('Switched to VOICE mode');
//    window.ipcRenderer?.send('switch-mode', 'voice');
//});

// ---------------------------
// CHAT PANEL TOGGLE
// ---------------------------
//panelToggle.addEventListener('click', async () => {
//    chatbotPanel.classList.toggle('hidden'); // show/hide panel
//
//    if(!chatbotPanel.classList.contains('hidden')){
//        // Tell main process to enter side panel mode (fix width, float on top)
//        await ipcRenderer.invoke('toggle-panel');
//    }
//});
//
//panelClosed.addEventListener('click', async () => {
//    chatbotPanel.classList.toggle('hidden'); // show/hide panel
//
//    if(chatbotPanel.classList.contains('hidden')){
//        // Tell main process to enter side panel mode (fix width, float on top)
//        await ipcRenderer.invoke('toggle-panel');
//    }
//});

// ---------------------------
// CHAT INPUT HANDLING
// ---------------------------
//input.addEventListener('keydown', (e) => {
//    if(e.key === 'Enter' && input.value.trim()){
//        // Add user message
//        const msg = document.createElement('div');
//        msg.className = 'user';
//        msg.textContent = input.value;
//        chatBody.appendChild(msg);

        // Reset input
//        input.value = '';
//        chatBody.scrollTop = chatBody.scrollHeight;
//
//        // Here you can add bot responses later
//        // Example placeholder:
//        setTimeout(() => {
//            const botMsg = document.createElement('div');
//            botMsg.className = 'bot';
//            botMsg.textContent = "Command received.";
//            chatBody.appendChild(botMsg);
//           chatBody.scrollTop = chatBody.scrollHeight;
//        }, 300);
//    }
//});

// ---------------------------
// APPLY CURRENT THEME TO PANEL IMMEDIATELY
// ---------------------------
//this function when dark theme is selected, the varibales in css can be chnaged
//NOT USED NOW
function applyThemeToPanel(){
    if(document.documentElement.getAttribute('data-theme') === 'dark'){
        chatbotPanel.style.backgroundColor = 'var(--bg-color)';
        chatbotPanel.style.color = 'var(--text-color)';
    } else {
        chatbotPanel.style.backgroundColor = 'var(--bg-color)';
        chatbotPanel.style.color = 'var(--text-color)';
    }
}

// Update on theme toggle
//btn.addEventListener('click', applyThemeToPanel);
//applyThemeToPanel();



//for signal graph
window.addEventListener('DOMContentLoaded', () => {

    const canvas1 = document.getElementById('eegChart1');
    const canvas2 = document.getElementById('eegChart2');

    if (!canvas1 || !canvas2) return;

    const eegChart1 = new SmoothieChart({
        millisPerPixel: 20,
        grid: { strokeStyle: '#555', lineWidth: 1 },
        labels: { fillStyle: '#AAA' },
        maxValue: 1,
        minValue: -1,
        interpolation: 'linear',
        maxDataSetLength: 500
    });

    const eegChart2 = new SmoothieChart({
        millisPerPixel: 20,
        grid: { strokeStyle: '#555', lineWidth: 1 },
        labels: { fillStyle: '#AAA' },
        maxValue: 1,
        minValue: -1,
        interpolation: 'linear',
        maxDataSetLength: 500
    });

    eegChart1.streamTo(canvas1, 1000);
    eegChart2.streamTo(canvas2, 1000);

    const verticalSeries = new TimeSeries();
    const horizontalSeries = new TimeSeries();

    eegChart1.addTimeSeries(verticalSeries, { strokeStyle: '#00fd98', lineWidth: 2 });
    eegChart2.addTimeSeries(horizontalSeries, { strokeStyle: '#00fd98', lineWidth: 2 });

    // WebSocket
    


    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.stat !== "ACTIVE"){
            console.log("NOT ACTIVE");
            return;
        }

        const now = Date.now();
        count++
        verticalSeries.append(now, msg.v);
        horizontalSeries.append(now, msg.h);
        showDirection(msg.dir_x,msg.dir_y)
    };

    document.getElementById("save-settings").addEventListener("click", () => {
        const settings = getSettings();
        saveSettings(settings);
        ipcRenderer.send("restart-python");
    });
});

//for the settings button on top bar
settingsbtn.addEventListener('click',()=>{
        window.api.openSettings();
})



//webscoket from python



function showDirection(dir_x,dir_y){

    document.querySelectorAll(".arrow").forEach(a=>{
        a.classList.remove("active");
    });

    if(dir_y === "UP") document.getElementById("up").classList.add("active");
    if(dir_y === "DOWN") document.getElementById("down").classList.add("active");
    if(dir_x === "LEFT") document.getElementById("left").classList.add("active");
    if(dir_x === "RIGHT") document.getElementById("right").classList.add("active");

}


function getSettings() {

    const settings = {
        moveAmount: parseFloat(document.getElementById("move-amount").value),
        slopeThreshold: parseFloat(document.getElementById("slope-threshold").value),
        neutralZone: parseFloat(document.getElementById("neutral-zone").value)
    };

    return settings;
}




function saveSettings(settings){
    console.log("Settings saved");
    fs.writeFileSync(
        "settings.json",
        JSON.stringify(settings, null, 4)
    );

    

}

