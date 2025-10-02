const fs = require('fs');

// Read the HTML file
const htmlContent = fs.readFileSync('./app/templates/orders/index.html', 'utf8');

// Extract JavaScript content between <script> tags
const scriptMatches = htmlContent.match(/<script[^>]*>([\s\S]*?)<\/script>/g);

if (scriptMatches && scriptMatches.length > 0) {
  // Get the content of the first script tag (main one)
  const scriptContent = scriptMatches[0].replace(/<script[^>]*>|<\/script>/g, '');
  
  try {
    // Try to parse the JavaScript content
    new Function(scriptContent);
    console.log('JavaScript syntax is valid');
  } catch (error) {
    console.log('JavaScript syntax error found:');
    console.log('Error:', error.message);
    console.log('Line:', error.lineNumber);
  }
} else {
  console.log('No script tags found');
}