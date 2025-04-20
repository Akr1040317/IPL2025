// src/components/Signup.jsx
import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { auth, googleProvider, db } from "../firebase";
import {
  createUserWithEmailAndPassword,
  signInWithPopup,
} from "firebase/auth";
import { doc, setDoc, query, collection, where, getDocs } from "firebase/firestore";
import debounce from "lodash.debounce";

export default function Signup() {
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [error, setError] = useState("");
  const [duplicateError, setDuplicateError] = useState({
    username: "",
    email: "",
  });
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const checkForDuplicates = debounce(async () => {
    setDuplicateError({ username: "", email: "" });

    // Check for duplicate username
    if (formData.username) {
      const usernameQuery = query(
        collection(db, "users"),
        where("username", "==", formData.username)
      );
      const usernameSnapshot = await getDocs(usernameQuery);
      if (!usernameSnapshot.empty) {
        setDuplicateError((prev) => ({
          ...prev,
          username: "Username already exists",
        }));
      }
    }

    // Check for duplicate email
    if (formData.email) {
      const emailQuery = query(
        collection(db, "users"),
        where("email", "==", formData.email)
      );
      const emailSnapshot = await getDocs(emailQuery);
      if (!emailSnapshot.empty) {
        setDuplicateError((prev) => ({
          ...prev,
          email: "Email already exists",
        }));
      }
    }
  }, 500);

  useEffect(() => {
    checkForDuplicates();
    return () => checkForDuplicates.cancel();
  }, [formData.username, formData.email]);

  const handleEmailSignup = async (e) => {
    e.preventDefault();
    setError("");
    if (formData.password !== formData.confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (duplicateError.username || duplicateError.email) {
      setError("Please resolve the errors above");
      return;
    }
    try {
      const userCredential = await createUserWithEmailAndPassword(
        auth,
        formData.email,
        formData.password
      );
      const user = userCredential.user;
      // Store user data in Firestore
      await setDoc(doc(db, "users", user.uid), {
        userId: user.uid,
        username: formData.username,
        email: formData.email,
        createdAt: new Date().toISOString(),
        method: "email",
      });
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  };

  const handleGoogleSignup = async () => {
    setError("");
    try {
      const result = await signInWithPopup(auth, googleProvider);
      const user = result.user;
      // Check if user already exists in Firestore
      const userDoc = await getDocs(
        query(collection(db, "users"), where("email", "==", user.email))
      );
      if (userDoc.empty) {
        // Generate a username from the email
        const generatedUsername = user.email.split("@")[0];
        // Check if the generated username already exists
        let finalUsername = generatedUsername;
        let usernameExists = true;
        let counter = 1;
        while (usernameExists) {
          const usernameQuery = query(
            collection(db, "users"),
            where("username", "==", finalUsername)
          );
          const usernameSnapshot = await getDocs(usernameQuery);
          if (usernameSnapshot.empty) {
            usernameExists = false;
          } else {
            finalUsername = `${generatedUsername}${counter}`;
            counter++;
          }
        }
        // Store user data in Firestore
        await setDoc(doc(db, "users", user.uid), {
          userId: user.uid,
          username: finalUsername,
          email: user.email,
          createdAt: new Date().toISOString(),
          method: "google",
        });
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen w-full min-w-80 flex-col bg-[#0d1a35] dark:bg-[#0d1a35] dark:text-white">
      <main className="flex max-w-full flex-auto flex-col items-center justify-center">
        <div className="relative container mx-auto px-4 py-12 lg:px-8 lg:py-16 xl:max-w-6xl">
          {/* Heading */}
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-8 text-center">
              <Link
                to="/"
                className="group inline-flex items-center gap-1.5 text-xl font-bold text-white hover:opacity-75 active:opacity-100 dark:text-white"
              >
                <img
                  src="https://www.iplt20.com/assets/images/ipl-logo-new-old.png"
                  alt="IPL Logo"
                  className="inline-block h-12 w-auto transition duration-150 ease-out group-hover:scale-105 group-active:scale-100"
                />
                <span className="text-2xl font-bold">IPL FanZone</span>
              </Link>
            </div>
            <div className="mb-5 flex items-center justify-center">
              <div className="inline-flex items-center gap-2 rounded-full bg-white/20 py-1.5 pr-3 pl-1.5 text-sm font-medium text-white dark:bg-white/10 dark:text-white">
                <span className="inline-flex items-center justify-center rounded-full bg-[#f5a623] px-2 py-1.5 text-xs leading-none font-medium text-[#0d1a35]">
                  Get Started
                </span>
                <span>Sign up for IPL FanZone</span>
              </div>
            </div>
            <div>
              <h1 className="mb-4 text-4xl font-black text-white dark:text-white">
                Create your IPL FanZone Account
              </h1>
              <h2 className="text-lg/relaxed font-medium text-gray-200 dark:text-gray-200">
                Join IPL fans to track teams and stats!
              </h2>
            </div>
          </div>
          {/* Signup Form */}
          <div className="relative mx-auto mt-10 max-w-lg">
            <div className="absolute inset-0 -inset-x-6 rounded-3xl bg-gradient-to-b from-[#f5a623] via-[#e91e63] to-[#f7c948] opacity-15 blur-xl"></div>
            <div className="relative rounded-2xl bg-white/40 p-2.5 ring-1 ring-gray-200/50 backdrop-blur-xs dark:bg-white/10 dark:ring-gray-200/20">
              <form
                onSubmit={handleEmailSignup}
                className="rounded-xl bg-white p-6 lg:p-12 dark:bg-[#0d1a35]"
              >
                {error && (
                  <div className="mb-4 text-center text-sm text-red-500">
                    {error}
                  </div>
                )}
                <div className="flex flex-col gap-5">
                  <div className="space-y-1">
                    <label
                      htmlFor="username"
                      className="inline-block text-sm font-medium text-gray-800 dark:text-white"
                    >
                      Username
                    </label>
                    <input
                      type="text"
                      id="username"
                      name="username"
                      value={formData.username}
                      onChange={handleChange}
                      className="block w-full rounded-lg border border-gray-200 px-3 py-2.5 leading-6 placeholder-gray-500 focus:border-[#f5a623] focus:ring-3 focus:ring-[#f5a623]/25 dark:border-gray-200/20 dark:bg-[#0d1a35] dark:placeholder-gray-400 dark:focus:border-[#f5a623] dark:text-white"
                      placeholder="Enter your username"
                      required
                    />
                    {duplicateError.username && (
                      <p className="text-sm text-red-500">
                        {duplicateError.username}
                      </p>
                    )}
                  </div>
                  <div className="space-y-1">
                    <label
                      htmlFor="email"
                      className="inline-block text-sm font-medium text-gray-800 dark:text-white"
                    >
                      Email
                    </label>
                    <input
                      type="email"
                      id="email"
                      name="email"
                      value={formData.email}
                      onChange={handleChange}
                      className="block w-full rounded-lg border border-gray-200 px-3 py-2.5 leading-6 placeholder-gray-500 focus:border-[#f5a623] focus:ring-3 focus:ring-[#f5a623]/25 dark:border-gray-200/20 dark:bg-[#0d1a35] dark:placeholder-gray-400 dark:focus:border-[#f5a623] dark:text-white"
                      placeholder="Enter your email"
                      required
                    />
                    {duplicateError.email && (
                      <p className="text-sm text-red-500">
                        {duplicateError.email}
                      </p>
                    )}
                  </div>
                  <div className="space-y-1">
                    <label
                      htmlFor="password"
                      className="inline-block text-sm font-medium text-gray-800 dark:text-white"
                    >
                      Password
                    </label>
                    <input
                      type="password"
                      id="password"
                      name="password"
                      value={formData.password}
                      onChange={handleChange}
                      className="block w-full rounded-lg border border-gray-200 px-3 py-2.5 leading-6 placeholder-gray-500 focus:border-[#f5a623] focus:ring-3 focus:ring-[#f5a623]/25 dark:border-gray-200/20 dark:bg-[#0d1a35] dark:placeholder-gray-400 dark:focus:border-[#f5a623] dark:text-white"
                      placeholder="Enter your password"
                      required
                    />
                  </div>
                  <div className="space-y-1">
                    <label
                      htmlFor="confirmPassword"
                      className="inline-block text-sm font-medium text-gray-800 dark:text-white"
                    >
                      Confirm Password
                    </label>
                    <input
                      type="password"
                      id="confirmPassword"
                      name="confirmPassword"
                      value={formData.confirmPassword}
                      onChange={handleChange}
                      className="block w-full rounded-lg border border-gray-200 px-3 py-2.5 leading-6 placeholder-gray-500 focus:border-[#f5a623] focus:ring-3 focus:ring-[#f5a623]/25 dark:border-gray-200/20 dark:bg-[#0d1a35] dark:placeholder-gray-400 dark:focus:border-[#f5a623] dark:text-white"
                      placeholder="Confirm your password"
                      required
                    />
                  </div>
                  <div>
                    <button
                      type="submit"
                      className="group flex w-full items-center justify-center gap-2 rounded-full border border-[#f5a623] bg-[#f5a623] px-4 py-3 text-sm leading-5 font-semibold text-[#0d1a35] hover:border-[#e91e63] hover:bg-[#e91e63] hover:text-white focus:ring-3 focus:ring-[#f5a623]/50 active:border-[#f5a623] active:bg-[#f5a623] dark:border-[#f5a623] dark:bg-[#f5a623] dark:text-[#0d1a35] dark:hover:border-[#e91e63] dark:hover:bg-[#e91e63] dark:hover:text-white dark:focus:ring-[#f5a623]/90 dark:active:border-[#f5a623] dark:active:bg-[#f5a623]"
                    >
                      <span>Sign up</span>
                    </button>
                  </div>
                  <div>
                    <button
                      type="button"
                      onClick={handleGoogleSignup}
                      className="group flex w-full items-center justify-center gap-2 rounded-full border border-[#f5a623] bg-transparent px-4 py-3 text-sm leading-5 font-semibold text-[#f5a623] hover:bg-[#f5a623] hover:text-[#0d1a35] focus:ring-3 focus:ring-[#f5a623]/50 active:bg-transparent active:text-[#f5a623] dark:border-[#f5a623] dark:text-[#f5a623] dark:hover:bg-[#f5a623] dark:hover:text-[#0d1a35] dark:focus:ring-[#f5a623]/90 dark:active:bg-transparent dark:active:text-[#f5a623]"
                    >
                      <svg
                        className="h-5 w-5"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                      >
                        <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-8.667 0-.76-.053-1.467-.173-2.053H12.48z" />
                      </svg>
                      <span>Sign up with Google</span>
                    </button>
                  </div>
                  <div className="text-center text-sm">
                    <span className="text-gray-800 dark:text-white">
                      Already have an account?{" "}
                    </span>
                    <Link
                      to="/login"
                      className="font-medium text-gray-600 hover:text-[#f5a623] dark:text-gray-200 dark:hover:text-[#f5a623]"
                    >
                      Sign in
                    </Link>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}