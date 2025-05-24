"use strict";

// Utility: shorthand for document.getElementById
const $ = (id) => document.getElementById(id);

const capitalizeFirstLetter = (string) =>
  string.charAt(0).toUpperCase() + string.slice(1); 