// src/firebase.js
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCwVBHZR2qvEIywjWqCVhlQGgRGd8XK1ZE",
  authDomain: "ipl2025-5f153.firebaseapp.com",
  projectId: "ipl2025-5f153",
  storageBucket: "ipl2025-5f153.firebasestorage.app",
  messagingSenderId: "1023543488605",
  appId: "1:1023543488605:web:45a6c627c5e475eea71db4",
  measurementId: "G-XET8HK7LHK",
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();
const db = getFirestore(app);

export { auth, googleProvider, db };