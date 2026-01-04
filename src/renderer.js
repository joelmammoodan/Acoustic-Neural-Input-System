const { ipcRenderer } = require('electron');

// DOM Elements
const btn = document.getElementById('theme-toggle');
const icon = document.getElementById('mode');
const brain_icon=document.getElementById('brain-img');
const currentTheme = localStorage.getItem('theme');

const panelToggle = document.getElementById("panel-toggle");
const panelClosed=document.getElementById('panel-close');
const chatbotPanel = document.getElementById("chatbot-panel");
const input = document.getElementById("chat-input");
const chatBody = document.getElementById("chat-body");

//const brainBtn = document.getElementById('brainBtn');
//const voiceBtn = document.getElementById('voiceBtn');


function cssVar(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

// ---------------------------
// THEME HANDLING
// ---------------------------
if(currentTheme === 'dark'){
    document.documentElement.setAttribute('data-theme','dark');
    icon.src = '../Icons/sun.png';
    brain_icon.src='../Icons/brain_black.png';
    

} else {
    document.documentElement.removeAttribute('data-theme');
    icon.src = '../Icons/moon.png';
    brain_icon.src='../Icons/brain_white.png';
    

}

btn.addEventListener('click', () => {
    let theme = document.documentElement.getAttribute('data-theme');

    if(theme === 'dark'){
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme','light');
        icon.src = '../Icons/moon.png';
        brain_icon.src='../Icons/brain_white.png';
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        icon.src = '../Icons/sun.png';
        brain_icon.src='../Icons/brain_black.png';
    }
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
panelToggle.addEventListener('click', async () => {
    chatbotPanel.classList.toggle('hidden'); // show/hide panel

    if(!chatbotPanel.classList.contains('hidden')){
        // Tell main process to enter side panel mode (fix width, float on top)
        await ipcRenderer.invoke('toggle-panel');
    }
});

panelClosed.addEventListener('click', async () => {
    chatbotPanel.classList.toggle('hidden'); // show/hide panel

    if(chatbotPanel.classList.contains('hidden')){
        // Tell main process to enter side panel mode (fix width, float on top)
        await ipcRenderer.invoke('toggle-panel');
    }
});

// ---------------------------
// CHAT INPUT HANDLING
// ---------------------------
input.addEventListener('keydown', (e) => {
    if(e.key === 'Enter' && input.value.trim()){
        // Add user message
        const msg = document.createElement('div');
        msg.className = 'user';
        msg.textContent = input.value;
        chatBody.appendChild(msg);

        // Reset input
        input.value = '';
        chatBody.scrollTop = chatBody.scrollHeight;

        // Here you can add bot responses later
        // Example placeholder:
        setTimeout(() => {
            const botMsg = document.createElement('div');
            botMsg.className = 'bot';
            botMsg.textContent = "Command received.";
            chatBody.appendChild(botMsg);
            chatBody.scrollTop = chatBody.scrollHeight;
        }, 300);
    }
});

// ---------------------------
// APPLY CURRENT THEME TO PANEL IMMEDIATELY
// ---------------------------
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
btn.addEventListener('click', applyThemeToPanel);
applyThemeToPanel();

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
