const queryInput = document.getElementById('query');
const form = document.getElementById('chat-form');
const statusDiv = document.getElementById('status');
let isProcessing = false;
let isAudioPlaying = false;
let isRecognitionActive = false;
let recognition = null;

if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    let silenceTimer = null;
    const SILENCE_THRESHOLD = 1500;
    const TERMINATION_PHRASES = ['stop listening', 'bye', 'exit'];
    const RESUME_PHRASE = 'start listening';
    const MAX_RETRIES = 3;
    const RETRY_BASE_DELAY = 500;

    // Function to start recognition with exponential backoff retries
    async function startRecognition(attempt = 1) {
        if (isAudioPlaying || isRecognitionActive) {
            console.log(`Cannot start recognition: audioPlaying=${isAudioPlaying}, recognitionActive=${isRecognitionActive}`);
            return;
        }

        const hasPermission = await checkMicPermission();
        if (!hasPermission) {
            statusDiv.textContent = 'Microphone access denied. Please click "Enable Microphone" to allow access.';
            return;
        }

        try {
            recognition.start();
            isRecognitionActive = true;
            statusDiv.textContent = 'Listening... Speak now.';
            console.log('Speech recognition started successfully');
        } catch (error) {
            console.error(`Attempt ${attempt} to start recognition failed: ${error.message}`);
            if (attempt <= MAX_RETRIES) {
                const delay = RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
                console.log(`Retrying recognition start in ${delay}ms (attempt ${attempt}/${MAX_RETRIES})`);
                setTimeout(() => startRecognition(attempt + 1), delay);
            } else {
                statusDiv.textContent = 'Failed to start microphone after retries. Please click "Enable Microphone".';
                console.error('Max retries reached for recognition start');
            }
        }
    }

    // Check microphone permission
    async function checkMicPermission() {
        try {
            const permissionStatus = await navigator.permissions.query({ name: 'microphone' });
            console.log('Microphone permission state:', permissionStatus.state);
            if (permissionStatus.state === 'denied') {
                console.log('Microphone permission denied');
                return false;
            }
            return true;
        } catch (error) {
            console.error('Error checking microphone permission:', error.message);
            statusDiv.textContent = 'Error checking microphone permission. Please ensure access is granted.';
            return false;
        }
    }

    // Request microphone permission
    window.requestMicPermission = async function() {
        try {
            await navigator.mediaDevices.getUserMedia({ audio: true });
            statusDiv.textContent = 'Microphone access granted. Listening...';
            startRecognition();
        } catch (error) {
            statusDiv.textContent = 'Microphone access denied. Please allow microphone access in browser settings.';
            console.error('Microphone permission error:', error.message);
        }
    };

    recognition.onstart = () => {
        if (!isAudioPlaying) {
            isRecognitionActive = true;
            statusDiv.textContent = 'Listening... Speak now.';
            console.log('Speech recognition started');
        }
    };

    recognition.onresult = (event) => {
        if (isAudioPlaying) {
            console.log('Ignoring speech recognition results during audio playback');
            return;
        }

        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.trim().toLowerCase();
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        queryInput.value = finalTranscript || interimTranscript;

        if (TERMINATION_PHRASES.some(phrase => finalTranscript.includes(phrase))) {
            recognition.stop();
            isRecognitionActive = false;
            statusDiv.textContent = 'Stopped listening. Say "start listening" or click "Enable Microphone".';
            queryInput.value = '';
            console.log('Recognition stopped due to termination phrase');
            return;
        }

        if (finalTranscript && !isProcessing && finalTranscript.length > 2) {
            clearTimeout(silenceTimer);
            silenceTimer = setTimeout(() => {
                if (!isProcessing && !isAudioPlaying) {
                    isProcessing = true;
                    queryInput.value = finalTranscript;
                    console.log('Submitting query:', finalTranscript);
                    form.submit();
                }
            }, SILENCE_THRESHOLD);
        }
    };

    recognition.onend = () => {
        isRecognitionActive = false;
        console.log('Recognition ended, isAudioPlaying:', isAudioPlaying);
        if (!isAudioPlaying && !TERMINATION_PHRASES.some(phrase => queryInput.value.toLowerCase().includes(phrase))) {
            startRecognition();
        }
        isProcessing = false;
    };

    recognition.onerror = (event) => {
        isRecognitionActive = false;
        console.error('Speech recognition error:', event.error);
        statusDiv.textContent = `Error: ${event.error}. Retrying...`;
        if (!isAudioPlaying) {
            startRecognition();
        }
    };

    queryInput.addEventListener('input', () => {
        if (queryInput.value.toLowerCase().includes(RESUME_PHRASE) && !isRecognitionActive) {
            startRecognition();
            queryInput.value = '';
            console.log('Recognition resumed via resume phrase');
        }
    });

    form.addEventListener('submit', () => {
        setTimeout(() => {
            queryInput.value = '';
            console.log('Textbox cleared after form submission');
        }, 100);
    });

    // Initial permission check and start
    checkMicPermission().then(hasPermission => {
        if (hasPermission) {
            startRecognition();
        } else {
            statusDiv.textContent = 'Please click "Enable Microphone" to start.';
        }
    });
} else {
    statusDiv.textContent = 'Your browser does not support speech recognition.';
    queryInput.readOnly = false;
    console.warn('Speech recognition not supported');
}

document.addEventListener('DOMContentLoaded', () => {
    const audio = document.getElementById('response-audio');
    if (audio) {
        audio.onplay = () => {
            isAudioPlaying = true;
            if (isRecognitionActive) {
                recognition.stop();
                isRecognitionActive = false;
                console.log('Recognition stopped during audio playback');
            }
            statusDiv.textContent = 'Playing response...';
        };
        audio.onended = () => {
            isAudioPlaying = false;
            isProcessing = false;
            queryInput.value = '';
            console.log('Audio playback ended, clearing textbox');
            if (!TERMINATION_PHRASES.some(phrase => queryInput.value.toLowerCase().includes(phrase))) {
                checkMicPermission().then(hasPermission => {
                    if (hasPermission && !isRecognitionActive) {
                        startRecognition();
                        console.log('Recognition started automatically after audio playback');
                    }
                });
            }
        };
        audio.onerror = () => {
            isAudioPlaying = false;
            isProcessing = false;
            queryInput.value = '';
            console.log('Audio playback error, clearing textbox');
            statusDiv.textContent = 'Error playing audio. Listening resumed.';
            checkMicPermission().then(hasPermission => {
                if (hasPermission && !isRecognitionActive) {
                    startRecognition();
                    console.log('Recognition started after audio error');
                }
            });
        };
    }
});