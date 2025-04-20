// src/App.jsx
import { Route, Routes, useNavigate } from "react-router-dom";
import { getAuth, getRedirectResult } from "firebase/auth";
import { useEffect } from "react";
import Login from "./components/Login";
import Signup from "./components/Signup";
import Dashboard from "./components/Dashboard";

function App() {
  const navigate = useNavigate();
  const auth = getAuth();

  useEffect(() => {
    // Handle redirect result after Google sign-in
    getRedirectResult(auth)
      .then((result) => {
        if (result) {
          navigate("/dashboard");
        }
      })
      .catch((error) => {
        console.error("Redirect Error:", error);
      });
  }, [auth, navigate]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/" element={<Login />} />
    </Routes>
  );
}

export default App;