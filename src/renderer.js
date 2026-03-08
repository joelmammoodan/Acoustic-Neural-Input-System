

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
window.addEventListener('DOMContentLoaded',()=>{
    const canvas=document.getElementById('eegChart');
    if(!canvas) return;

    const ctx=canvas.getContext('2d');

    const MAX_POINTS=500;
    const data=[];
    const labels=[];

    const eegChart=new Chart(ctx,{
        type:'line',
        data:{
            labels,
            datasets:[{
                label:'C3',
                data,
                borderColor:'#00fd98',
                borderWidth:1,
                pointRadius:0,
                tension:0
            }]
        },
        options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { display: false },
                y: {
                min: -200,
                max: 200,
                title: { display: true, text: "Amplitude" }
                }
            }
        }
    });

    let t = 0;
        setInterval(() => {
            if (data.length >= MAX_POINTS) {
            data.shift();
            labels.shift();
            }

            labels.push(t++);
            data.push(
            50 * Math.sin(2 * Math.PI * 10 * t / 250) +
            (Math.random() - 0.5) * 15
            );

            eegChart.update("none");
        }, 4);



});


//for the settings button on top bar
settingsbtn.addEventListener('click',()=>{
        window.api.openSettings();
})



//webscoket from python

const ws = new WebSocket("ws://localhost:8765")

ws.onmessage= (event) =>{
    const signal=event.data
    console.log(signal)
}


