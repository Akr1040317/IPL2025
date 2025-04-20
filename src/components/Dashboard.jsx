import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { auth, db } from "../firebase";
import { signOut } from "firebase/auth";
import { onAuthStateChanged } from "firebase/auth";
import { doc, getDoc, updateDoc } from "firebase/firestore";
import { Menu, MenuButton, MenuItems, MenuItem, Transition } from "@headlessui/react";
import "./IPLPointsTable.css";

// Import all team logos
import cskLogo from "../assets/csk.avif";
import miLogo from "../assets/mi.avif";
import rcbLogo from "../assets/rcb.avif";
import kkrLogo from "../assets/kkr.avif";
import srhLogo from "../assets/srh.avif";
import dcLogo from "../assets/dc.avif";
import pbksLogo from "../assets/pk.avif";
import rrLogo from "../assets/rr.avif";
import gtLogo from "../assets/gt.avif";
import lsgLogo from "../assets/lsg.avif";
import defaultLogo from "../assets/defaultLogo.png";

// List of IPL teams with names and imported logo paths
const iplTeams = [
  { name: "Chennai Super Kings", logo: cskLogo },
  { name: "Mumbai Indians", logo: miLogo },
  { name: "Royal Challengers Bengaluru", logo: rcbLogo },
  { name: "Kolkata Knight Riders", logo: kkrLogo },
  { name: "Sunrisers Hyderabad", logo: srhLogo },
  { name: "Delhi Capitals", logo: dcLogo },
  { name: "Punjab Kings", logo: pbksLogo },
  { name: "Rajasthan Royals", logo: rrLogo },
  { name: "Gujarat Titans", logo: gtLogo },
  { name: "Lucknow Super Giants", logo: lsgLogo },
];

// Helper function to normalize team names and map abbreviations
const normalizeTeamName = (teamName) => {
  if (!teamName) return "";
  
  // If we got something like "Chennai Super Kings - 111 (15.3 ov)", strip score/off‑overs
  const raw = teamName.split(" - ")[0].trim();

  // First try an exact match on the canonical list
  const exact = iplTeams.find(t => t.name.toLowerCase() === raw.toLowerCase());
  if (exact) return exact.name.toLowerCase();

  // Next try the old abbreviation map
  
  // Extract team abbreviation from names like "PBKS - 111 (15.3 ov)" or just "MI"
  const teamAbbrMatch = teamName.match(/^[A-Z]+/);
  const teamAbbr = teamAbbrMatch ? teamAbbrMatch[0].toLowerCase() : teamName.trim().toLowerCase().replace(/\s+/g, "");

  const teamNameMap = {
    "csk": "chennai super kings",
    "mi": "mumbai indians",
    "rcb": "royal challengers bengaluru",
    "royalchallengersbangalore": "royal challengers bengaluru",
    "kkr": "kolkata knight riders",
    "srh": "sunrisers hyderabad",
    "dc": "delhi capitals",
    "pbks": "punjab kings",
    "rr": "rajasthan royals",
    "gt": "gujarat titans",
    "lsg": "lucknow super giants",
    "chennaisuperkings": "chennai super kings",
    "mumbaiindians": "mumbai indians",
    "royalchallengersbengaluru": "royal challengers bengaluru",
    "kolkataknightriders": "kolkata knight riders",
    "sunrisershyderabad": "sunrisers hyderabad",
    "delhicapitals": "delhi capitals",
    "punjabkings": "punjab kings",
    "rajasthanroyals": "rajasthan royals",
    "gujarattitans": "gujarat titans",
    "lucknowsupergiants": "lucknow super giants",
  };

  const mappedName = teamNameMap[teamAbbr] || teamAbbr;
  return iplTeams.find((t) => t.name.toLowerCase().replace(/\s+/g, "") === mappedName)?.name.toLowerCase() || mappedName;
};

// Helper function to get team logo by name
const getTeamLogo = (teamName) => {
  const normalizedTeamName = normalizeTeamName(teamName);
  console.log(`Original: ${teamName}, Normalized: ${normalizedTeamName}`);
  const team = iplTeams.find(
    (t) => t.name.toLowerCase() === normalizedTeamName
  );
  if (!team) {
    console.warn(`Team logo not found for: "${teamName}" (normalized: "${normalizedTeamName}")`);
    return defaultLogo;
  }
  return team.logo;
};

// IPL Points Table Component
const IPLPointsTable = ({ favoriteTeam }) => {
  const [standings, setStandings] = useState([]);
  const [simulate, setSimulate] = useState(false);
  const [pastMatches, setPastMatches] = useState([]);
  const [upcomingMatches, setUpcomingMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAllPastMatches, setShowAllPastMatches] = useState(false);
  const [showAllUpcomingMatches, setShowAllUpcomingMatches] = useState(false);  


  const getSimulatedStandings = () => {
    // Deep-clone current table rows
    const sim = standings.map(r => ({
      ...r,
      P: r.P,
      W: r.W,
      L: r.L,
      PTS: r.PTS,
      RECENT_FORM: r.RECENT_FORM.split(' ')
    }));
  
    // Helper to find row by team, using normalized team names
    const find = name => {
      const normalizedName = normalizeTeamName(name);
      const found = sim.find(r => normalizeTeamName(r.TEAM) === normalizedName);
      if (!found) {
        console.warn(`Team not found in standings: "${name}" (normalized: "${normalizedName}")`);
      }
      return found;
    };
  
    upcomingMatches.forEach(match => {
      const { Team_1, Team_2, Probability } = match;
      // Normalize team names
      const team1Normalized = normalizeTeamName(Team_1);
      const team2Normalized = normalizeTeamName(Team_2);
  
      // Use probabilities for weighted random selection
      const team1Prob = (Probability?.Team_1 ?? 50) / 100; // Convert to 0-1 scale
      const random = Math.random();
      const winner = random < team1Prob ? Team_1 : Team_2;
      const loser = winner === Team_1 ? Team_2 : Team_1;
  
      // Log the random selection for debugging
      console.log(`Match: ${Team_1} (${Probability?.Team_1}%) vs ${Team_2} (${Probability?.Team_2}%), Random: ${random.toFixed(3)}, Winner: ${winner}`);
  
      // Update winner
      const w = find(winner);
      if (w) {
        w.P += 1;
        w.W += 1;
        w.PTS += 2;
        w.RECENT_FORM.push('W');
      } else {
        console.warn(`Winner "${winner}" not found in standings`);
      }
  
      // Update loser
      const l = find(loser);
      if (l) {
        l.P += 1;
        l.L += 1;
        l.RECENT_FORM.push('L');
      } else {
        console.warn(`Loser "${loser}" not found in standings`);
      }
    });
  
    // Re-stringify recent form with spaces and sort
    sim.forEach(r => r.RECENT_FORM = r.RECENT_FORM.slice(-5).join(' '));
    sim.sort((a, b) => {
      if (b.PTS !== a.PTS) return b.PTS - a.PTS;
      return b.NRR - a.NRR;
    });
    // Reassign positions
    sim.forEach((r, i) => r.POS = i + 1);
    return sim;
  };

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch standings
        const standingsResponse = await fetch('http://localhost:5001/api/standings');
        if (!standingsResponse.ok) {
          throw new Error('Failed to fetch standings');
        }
        const standingsData = await standingsResponse.json();

        // Fetch past matches
        const pastMatchesResponse = await fetch('http://localhost:5001/api/matches');
        if (!pastMatchesResponse.ok) {
          throw new Error('Failed to fetch past matches');
        }
        const pastMatchesData = await pastMatchesResponse.json();

        // Fetch upcoming matches
        const upcomingMatchesResponse = await fetch('http://localhost:5001/api/upcoming-matches');
        if (!upcomingMatchesResponse.ok) {
          throw new Error('Failed to fetch upcoming matches');
        }
        const upcomingMatchesData = await upcomingMatchesResponse.json();

        setStandings(standingsData);
        setPastMatches(pastMatchesData);
        setUpcomingMatches(upcomingMatchesData);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  const renderRecentForm = (form) => {
    return form.split("").map((result, index) => (
      <span
        key={index}
        className={
          result === "W" ? "text-green-500 font-bold" : result === "L" ? "text-red-500 font-bold" : "text-gray-400"
        }
      >
        {result}
      </span>
    ));
  };
const teamColors = {
  "Chennai Super Kings": "#FCCA05",
  "Mumbai Indians":          "#0057A8",
  "Royal Challengers Bengaluru": "#DC143C",
  "Kolkata Knight Riders":   "#4D136C",
  "Sunrisers Hyderabad":     "#FF6200",
  "Delhi Capitals":          "#004C93",
  "Punjab Kings":            "#E03A3E",
  "Rajasthan Royals":        "#254AA5",
  "Gujarat Titans":          "#1C345A",
  "Lucknow Super Giants":    "#FFD700",
};
  const displayedPastMatches = showAllPastMatches ? pastMatches : pastMatches.slice(0, 6);
  const displayedUpcomingMatches = showAllUpcomingMatches ? upcomingMatches : upcomingMatches.slice(0, 6);

  return (

    <div className="ipl-points-table">
      <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-[#f5a623]">IPL 2025 Standings</h2>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={simulate}
              onChange={() => setSimulate(!simulate)}
            />
            Predictive Simulation
          </label>
        </div>
      <div className="overflow-x-auto">
      <table className="min-w-full bg-[#1a2a5b] text-white">
          <thead>
            <tr>
              {[
                "POS","Team","P","W","L","NR","NRR","For","Against","PTS","Recent Form"
              ].map((h, i) => (
                <th
                  key={i}
                  className="px-4 py-2 border-b border-gray-700"
                  style={h === "Team" ? { textAlign: "left" } : {}}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
          {(simulate ? getSimulatedStandings() : standings).map((row, idx) => {
              const isFav     = row.TEAM === favoriteTeam;
              const color     = teamColors[row.TEAM];
              const baseStyle = isFav
                ? {
                    borderTop:    `8px solid ${color}`,
                    borderBottom: `8px solid ${color}`,
                  }
                : {};

              return (
                <tr key={idx} className="hover:bg-[#2a3b7b]">
                  {/* POS cell (first) */}
                  <td
                    className="px-4 py-2 border-gray-700 text-center"
                    style={{
                      ...baseStyle,
                      ...(isFav && {
                        borderLeft:            `8px solid ${color}`,
                        borderTopLeftRadius:   "2rem",
                        borderBottomLeftRadius:"2rem",
                      }),
                    }}
                  >
                    <div className="flex items-center justify-center gap-2">
                      {row.POS <= 4 && (
                        <span className="w-3 h-3 bg-green-500 rounded-full"></span>
                      )}
                      {row.POS}
                    </div>
                  </td>

                  {/* Team name */}
                  <td
                    className="px-4 py-2 border-gray-700"
                    style={baseStyle}
                  >
                    {row.TEAM}
                  </td>

                  {[row.P, row.W, row.L, row.NR, row.NRR, row.FOR, row.AGAINST, row.PTS].map(
                    (val, i) => (
                      <td
                        key={i}
                        className="px-4 py-2 border-gray-700 text-center"
                        style={baseStyle}
                      >
                        {val}
                      </td>
                    )
                  )}

                  {/* Recent Form (last cell) */}
                  <td
                    className="px-4 py-2 border-gray-700 text-center"
                    style={{
                      ...baseStyle,
                      ...(isFav && {
                        borderRight:           `8px solid ${color}`,
                        borderTopRightRadius:  "2rem",
                        borderBottomRightRadius:"2rem",
                      }),
                    }}
                  >
                    {row.RECENT_FORM.split("").map((r, i) => (
                      <span
                        key={i}
                        className={
                          r === "W"
                            ? "text-green-500 font-bold"
                            : r === "L"
                            ? "text-red-500 font-bold"
                            : "text-gray-400"
                        }
                      >
                        {r}
                      </span>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Upcoming Matches Section */}
      <h2 className="text-2xl font-bold text-[#f5a623] mt-8 mb-4">IPL 2025 Upcoming Matches</h2>
      {upcomingMatches.length > 0 ? (
        <>
          <div className="space-y-4">
            {displayedUpcomingMatches.map((match, index) => {
              // Use scraped probability data
              const prob = match.Probability || { Team_1: 50.0, Team_2: 50.0 };
              const likelyWinner = prob.Team_1 > prob.Team_2 ? match.Team_1 : match.Team_2;

              return (
                <div
                  key={index}
                  className="bg-white text-black rounded-lg p-4 flex items-center justify-between match-card"
                >
                  <div className="flex items-center gap-4">
                    <div className="text-sm text-gray-600">
                      <div className="flex items-center gap-2">
                        <svg
                          className="w-5 h-5 text-gray-400"
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                          />
                        </svg>
                        <span>{match.Date_Time}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <svg
                          className="w-5 h-5 text-gray-400"
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M17.657 16.243l1.414-1.414-1.414-1.414M6.343 7.757L4.929 9.171l1.414 1.414M12 4v16M4 12h16"
                          />
                        </svg>
                        <span>{match.Location || "Location TBD"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-center gap-6 w-full max-w-md team-section">
                    <div className="flex items-center gap-2 team-block">
                      <img
                        src={getTeamLogo(match.Team_1)}
                        alt={`${match.Team_1} Logo`}
                        className="w-10 h-10 object-contain team-logo"
                      />
                      <span className="font-semibold text-sm team-name">{match.Team_1}</span>
                    </div>
                    <span className="text-gray-500 font-bold vs-text">vs</span>
                    <div className="flex items-center gap-2 team-block">
                      <span className="font-semibold text-sm team-name">{match.Team_2}</span>
                      <img
                        src={getTeamLogo(match.Team_2)}
                        alt={`${match.Team_2} Logo`}
                        className="w-10 h-10 object-contain team-logo"
                      />
                    </div>
                  </div>

                  <div className="probability-container">
                    <div className="probability-teams">
                      <div className="probability-team">
                        <strong>
                          {match.Team_1} {prob.Team_1.toFixed(2)}%
                          {prob.Team_1 > prob.Team_2 && (
                            <span className="probability-icon">
                              <svg
                                className="w-4 h-4 text-green-500 inline-block ml-1"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                xmlns="http://www.w3.org/2000/svg"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                  d="M5 13l4 4L19 7"
                                />
                              </svg>
                            </span>
                          )}
                        </strong>
                      </div>
                      <div className="probability-team">
                        <strong>
                          {match.Team_2} {prob.Team_2.toFixed(2)}%
                          {prob.Team_2 > prob.Team_1 && (
                            <span className="probability-icon">
                              <svg
                                className="w-4 h-4 text-green-500 inline-block ml-1"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                xmlns="http://www.w3.org/2000/svg"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                  d="M5 13l4 4L19 7"
                                />
                              </svg>
                            </span>
                          )}
                        </strong>
                      </div>
                    </div>
                    <div className="probability-bar">
                      <div
                        className="probability-bar-fill team1"
                        style={{ width: `${prob.Team_1}%` }}
                      ></div>
                      <div
                        className="probability-bar-fill team2"
                        style={{ width: `${prob.Team_2}%` }}
                      ></div>
                    </div>
                    <div className="probability-label">Winning Probability</div>
                  </div>
                </div>
              );
            })}
          </div>

          {upcomingMatches.length > 6 && (
            <div className="mt-4 text-center">
              <button
                onClick={() => setShowAllUpcomingMatches(!showAllUpcomingMatches)}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#f5a623] px-4 py-2 text-sm font-semibold text-[#0d1a35] hover:bg-[#e91e63] hover:text-white focus:ring-3 focus:ring-[#f5a623]/40"
              >
                {showAllUpcomingMatches ? "Show Fewer Upcoming Matches" : "Show All Upcoming Matches"}
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="text-white text-center">No upcoming matches available.</div>
      )}

      {/* Past Matches Section */}
      <h2 className="text-2xl font-bold text-[#f5a623] mt-8 mb-4">IPL 2025 Past Matches</h2>
      <div className="space-y-4">
        {displayedPastMatches.map((match, index) => (
          <div
            key={index}
            className="bg-white text-black rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-4">
              <div className="text-sm text-gray-600">
                <div className="flex items-center gap-2">
                  <svg
                    className="w-5 h-5 text-gray-400"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                    />
                  </svg>
                  <span>{match.Date_Time}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <svg
                    className="w-5 h-5 text-gray-400"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M17.657 16.243l1.414-1.414-1.414-1.414M6.343 7.757L4.929 9.171l1.414 1.414M12 4v16M4 12h16"
                    />
                  </svg>
                  <span>{match.Location || "Location TBD"}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-center gap-6 w-full max-w-md team-section">
              <div className="flex items-center gap-2 team-block">
                <img
                  src={getTeamLogo(match.Team_1)}
                  alt={`${match.Team_1} Logo`}
                  className="w-10 h-10 object-contain team-logo"
                />
                <span className="font-semibold text-sm team-name">{match.Team_1}</span>
              </div>
              <span className="text-gray-500 font-bold vs-text">vs</span>
              <div className="flex items-center gap-2 team-block">
                <span className="font-semibold text-sm team-name">{match.Team_2}</span>
                <img
                  src={getTeamLogo(match.Team_2)}
                  alt={`${match.Team_2} Logo`}
                  className="w-10 h-10 object-contain team-logo"
                />
              </div>
            </div>

            <div className="text-sm font-medium">
              {match.Result || "Result TBD"}
            </div>
          </div>
        ))}
      </div>

      {pastMatches.length > 6 && (
        <div className="mt-4 text-center">
          <button
            onClick={() => setShowAllPastMatches(!showAllPastMatches)}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#f5a623] px-4 py-2 text-sm font-semibold text-[#0d1a35] hover:bg-[#e91e63] hover:text-white focus:ring-3 focus:ring-[#f5a623]/40"
          >
            {showAllPastMatches ? "Show Fewer Past Matches" : "Show All Past Matches"}
          </button>
        </div>
      )}
    </div>
  );
};

export default function Dashboard() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [favoriteTeam, setFavoriteTeam] = useState(null);

  // Brand‐colors for outlining the favorite‐team row
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (!user) {
        setFavoriteTeam(null);
        setShowModal(true);
        return;
      }
      const snap = await getDoc(doc(db, "users", user.uid));
      const fav  = snap.data()?.favoriteTeam;
      if (fav) {
        setFavoriteTeam(fav);
        setShowModal(false);
      } else {
        setFavoriteTeam(null);
        setShowModal(true);
      }
    });
    return unsubscribe;
  }, []);

  
  const handleTeamSelect = async (teamName) => {
    const user = auth.currentUser;
    if (user) {
      const userDocRef = doc(db, "users", user.uid);
      try {
        await updateDoc(userDocRef, {
          favoriteTeam: teamName,
        });
        setShowModal(false);
      } catch (err) {
        console.error("Error saving favorite team:", err.message);
      }
    }
  };

  const handleSignOut = async () => {
    try {
      await signOut(auth);
      navigate("/login");
    } catch (err) {
      console.error("Error signing out:", err.message);
    }
  };

  return (
    <>
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="relative rounded-2xl bg-[#1a2a5b] p-6 max-w-3xl w-full mx-4">
            <h2 className="text-2xl font-bold text-[#f5a623] mb-4 text-center">
              Select Your Favorite IPL Team
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
              {iplTeams.map((team) => (
                <button
                  key={team.name}
                  onClick={() => handleTeamSelect(team.name)}
                  className="flex flex-col items-center p-4 rounded-lg bg-[#061E57] hover:bg-[#3a4b9b] transition-colors"
                >
                  <img
                    src={team.logo}
                    alt={`${team.name} Logo`}
                    className="h-16 w-16 mb-2 object-contain"
                  />
                  <span className="text-white text-sm font-medium text-center">
                    {team.name}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div
        id="page-container"
        className={`mx-auto flex min-h-dvh w-full min-w-80 flex-col bg-[#0d1a35] dark:bg-[#0d1a35] dark:text-gray-100 ${
          desktopSidebarOpen ? "lg:pl-64" : ""
        }`}
      >
        <nav
          id="page-sidebar"
          aria-label="Main Sidebar Navigation"
          className={`fixed top-0 bottom-0 left-0 z-50 flex h-full w-full flex-col border-r border-gray-800 bg-[#1a2a5b] text-gray-200 transition-transform duration-500 ease-out lg:w-64 ${
            desktopSidebarOpen ? "lg:translate-x-0" : "lg:-translate-x-full"
          } ${mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <div className="flex h-16 w-full flex-none items-center justify-between bg-[#f5a623]/25 px-4 lg:justify-center">
            <Link
              to="/dashboard"
              className="group inline-flex items-center gap-2 text-lg font-bold tracking-wide text-white hover:opacity-75 active:opacity-100 dark:text-white"
            >
              <img
                src="https://www.iplt20.com/assets/images/ipl-logo-new-old.png"
                alt="IPL Logo"
                className="inline-block h-12 w-auto transition duration-150 ease-out group-hover:scale-105 group-active:scale-100"
              />
              <span className="text-xl font-bold">IPL FanZone</span>
            </Link>
            <div className="lg:hidden">
              <button
                onClick={() => setMobileSidebarOpen(false)}
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#f5a623] bg-[#1a2a5b] px-3 py-2 text-sm leading-5 font-semibold text-white hover:border-[#e91e63] hover:text-white hover:shadow-xs focus:ring-3 focus:ring-[#f5a623]/40 active:border-[#f5a623] active:shadow-none"
              >
                <svg
                  className="hi-mini hi-x-mark -mx-0.5 inline-block size-5"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </button>
            </div>
          </div>

          <div className="overflow-y-auto">
            <div className="w-full p-4">
              <nav className="space-y-1">
                <Link
                  to="/dashboard"
                  className="group flex items-center gap-2 rounded-lg border border-transparent bg-[#f5a623]/75 px-2.5 text-sm font-medium text-[#0d1a35]"
                >
                  <span className="flex flex-none items-center text-[#0d1a35]">
                    <svg
                      className="hi-outline hi-home inline-block size-5"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth="1.5"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
                      />
                    </svg>
                  </span>
                  <span className="grow py-2">Dashboard</span>
                </Link>
                <div className="px-3 pt-5 pb-2 text-xs font-semibold tracking-wider text-gray-400 uppercase">
                  Account
                </div>
                <Link
                  to="#"
                  className="group flex items-center gap-2 rounded-lg border border-transparent px-2.5 text-sm font-medium text-gray-200 hover:bg-[#f5a623]/75 hover:text-[#0d1a35] active:border-[#e91e63]"
                >
                  <span className="flex flex-none items-center text-gray-400 group-hover:text-[#0d1a35]">
                    <svg
                      className="hi-outline hi-user-circle inline-block size-5"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth="1.5"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                    </svg>
                  </span>
                  <span className="grow py-2">Profile</span>
                </Link>
                <button
                  onClick={handleSignOut}
                  className="group flex items-center gap-2 rounded-lg border border-transparent px-2.5 text-sm font-medium text-gray-200 hover:bg-[#f5a623]/75 hover:text-[#0d1a35] active:border-[#e91e63] w-full text-left"
                >
                  <span className="flex flex-none items-center text-gray-400 group-hover:text-[#0d1a35]">
                    <svg
                      className="hi-outline hi-lock-closed inline-block size-5"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth="1.5"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
                      />
                    </svg>
                  </span>
                  <span className="grow py-2">Sign out</span>
                </button>
              </nav>
            </div>
          </div>
        </nav>

        <header
          id="page-header"
          className={`fixed top-0 right-0 left-0 z-30 flex h-16 flex-none items-center bg-[#1a2a5b] shadow-sm dark:bg-[#1a2a5b] ${
            desktopSidebarOpen ? "lg:pl-64" : ""
          }`}
        >
          <div className="mx-auto flex w-full max-w-10xl justify-between px-4 lg:px-8">
            <div className="flex items-center gap-2">
              <div className="hidden lg:block">
                <button
                  onClick={() => setDesktopSidebarOpen(!desktopSidebarOpen)}
                  type="button"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#f5a623] bg-[#1a2a5b] px-3 py-2 text-sm leading-5 font-semibold text-white hover:border-[#e91e63] hover:text-white hover:shadow-xs focus:ring-3 focus:ring-[#f5a623]/40 active:border-[#f5a623] active:shadow-none"
                >
                  <svg
                    className="hi-solid hi-menu-alt-1 inline-block size-5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      fillRule="evenodd"
                      d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h6a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
              <div
  className="absolute inset-x-0 top-0 flex justify-center items-center h-16 pointer-events-none"
>
  {favoriteTeam && (
    <div className="flex items-center gap-2 pointer-events-auto">
      <span className="pl-4">Your team:</span>
      <img
        src={getTeamLogo(favoriteTeam)}
        alt={`${favoriteTeam} Logo`}
        className="h-8 w-8 object-contain"
      />
      <span className="text-white font-semibold">
        {favoriteTeam}
      </span>
      <button
          onClick={() => setShowModal(true)}
          className="p-1 rounded hover:bg-white/10"
          title="Change favorite team"
        >
          {/* pencil icon from Heroicons */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5 text-white"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
            <path
              fillRule="evenodd"
              d="M2 15a1 1 0 011-1h7v2H3a1 1 0 01-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </button>
    </div>
  )}
</div>
              <div className="lg:hidden">
                <button
                  onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
                  type="button"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#f5a623] bg-[#1a2a5b] px-3 py-2 text-sm leading-5 font-semibold text-white hover:border-[#e91e63] hover:text-white hover:shadow-xs focus:ring-3 focus:ring-[#f5a623]/40 active:border-[#f5a623] active:shadow-none"
                >
                  <svg
                    className="hi-solid hi-menu-alt-1 inline-block size-5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      fillRule="evenodd"
                      d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h6a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>
            <div className="flex items-center lg:hidden">
              <Link
                to="/dashboard"
                className="group inline-flex items-center gap-2 text-lg font-bold tracking-wide text-white hover:opacity-75 dark:text-white"
              >
                <img
                  src="https://www.iplt20.com/assets/images/ipl-logo-new-old.png"
                  alt="IPL Logo"
                  className="inline-block h-12 w-auto transition duration-150 ease-out group-hover:scale-105 group-active:scale-100"
                />
                <span className="hidden sm:inline text-xl font-bold">IPL FanZone</span>
              </Link>
            </div>
            <div className="flex items-center gap-2">
              <Menu as="div" className="relative inline-block">
                <MenuButton className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#f5a623] bg-[#1a2a5b] px-3 py-2 text-sm leading-5 font-semibold text-white hover:border-[#e91e63] hover:text-white hover:shadow-xs focus:ring-3 focus:ring-[#f5a623]/40 active:border-[#f5a623] active:shadow-none">
                  <svg
                    className="hi-mini hi-user-circle inline-block size-5 sm:hidden"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-5.5-2.5a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zM10 12a5.99 5.99 0 00-4.793 2.39A6.483 6.483 0 0010 16.5a6.483 6.483 0 004.793-2.11A5.99 5.99 0 0010 12z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <span className="hidden sm:inline">{auth.currentUser?.email.split("@")[0]}</span>
                  <svg
                    className="hi-mini hi-chevron-down hidden size-5 opacity-40 sm:inline-block"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </MenuButton>
                <Transition
                  enter="transition ease-out duration-100"
                  enterFrom="opacity-0 scale-90"
                  enterTo="opacity-100 scale-100"
                  leave="transition ease-in duration-75"
                  leaveFrom="opacity-100 scale-100"
                  leaveTo="opacity-0 scale-90"
                >
                  <MenuItems
                    modal={false}
                    className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-lg shadow-xl focus:outline-hidden dark:shadow-gray-900"
                  >
                    <div className="divide-y divide-gray-100 rounded-lg bg-white ring-1 ring-black/5 dark:divide-gray-700 dark:bg-[#1a2a5b] dark:ring-gray-700">
                      <div className="space-y-1 p-2.5">
                        <MenuItem>
                          {({ focus }) => (
                            <Link
                              to="#"
                              className={`group flex items-center justify-between gap-2 rounded-lg border border-transparent px-2.5 py-2 text-sm font-medium ${
                                focus
                                  ? "bg-[#f5a623] text-[#0d1a35] dark:border-transparent dark:bg-[#f5a623] dark:text-[#0d1a35]"
                                  : "text-white hover:bg-[#f5a623] hover:text-[#0d1a35] active:border-[#e91e63] dark:text-white dark:hover:bg-[#f5a623] dark:hover:text-[#0d1a35] dark:active:border-[#e91e63]"
                              }`}
                            >
                              <svg
                                className="hi-mini hi-user-circle inline-block size-5 flex-none opacity-25 group-hover:opacity-50"
                                xmlns="http://www.w3.org/2000/svg"
                                viewBox="0 0 20 20"
                                fill="currentColor"
                                aria-hidden="true"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-5.5-2.5a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zM10 12a5.99 5.99 0 00-4.793 2.39A6.483 6.483 0 0010 16.5a6.483 6.483 0 004.793-2.11A5.99 5.99 0 0010 12z"
                                  clipRule="evenodd"
                                />
                              </svg>
                              <span className="grow">Account</span>
                            </Link>
                          )}
                        </MenuItem>
                      </div>
                      <div className="space-y-1 p-2.5">
                        <MenuItem>
                          {({ focus }) => (
                            <button
                              onClick={handleSignOut}
                              className={`group flex items-center justify-between gap-2 rounded-lg border border-transparent px-2.5 py-2 text-sm font-medium w-full text-left ${
                                focus
                                  ? "bg-[#f5a623] text-[#0d1a35] dark:border-transparent dark:bg-[#f5a623] dark:text-[#0d1a35]"
                                  : "text-white hover:bg-[#f5a623] hover:text-[#0d1a35] active:border-[#e91e63] dark:text-white dark:hover:bg-[#f5a623] dark:hover:text-[#0d1a35] dark:active:border-[#e91e63]"
                              }`}
                            >
                              <svg
                                className="hi-mini hi-lock-closed inline-block size-5 flex-none opacity-25 group-hover:opacity-50"
                                xmlns="http://www.w3.org/2000/svg"
                                viewBox="0 0 20 20"
                                fill="currentColor"
                                aria-hidden="true"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
                                  clipRule="evenodd"
                                />
                              </svg>
                              <span className="grow">Sign out</span>
                            </button>
                          )}
                        </MenuItem>
                      </div>
                    </div>
                  </MenuItems>
                </Transition>
              </Menu>
            </div>
          </div>
        </header>

        <main
          id="page-content"
          className="flex max-w-full flex-auto flex-col pt-16"
        >
          <div className="mx-auto w-full max-w-10xl p-4 lg:p-8">
          <IPLPointsTable favoriteTeam={favoriteTeam} />
          </div>
        </main>

        <footer
          id="page-footer"
          className="flex flex-none items-center bg-[#1a2a5b] dark:bg-[#1a2a5b]"
        >
          <div className="mx-auto flex w-full max-w-10xl flex-col px-4 text-center text-sm text-white md:flex-row md:justify-between md:text-left lg:px-8">
            <div className="pt-4 pb-1 md:pb-4">
              <span className="font-medium text-[#f5a623] hover:text-[#e91e63]">
                IPL FanZone
              </span>{" "}
              © 2025
            </div>
            <div className="inline-flex items-center justify-center pt-1 pb-4 md:pt-4">
              <span>Crafted with</span>
              <svg
                className="hi-solid hi-heart mx-1 inline-block size-4 text-red-600"
                fill="currentColor"
                viewBox="0 0 20 20"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  fillRule="evenodd"
                  d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z"
                  clipRule="evenodd"
                />
              </svg>
              <span>
                by{" "}
                <span className="font-medium text-[#f5a623] hover:text-[#e91e63]">
                  Your Team
                </span>
              </span>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}