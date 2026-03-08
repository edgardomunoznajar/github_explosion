FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY favicon.png /usr/share/nginx/html/favicon.png
COPY og-image.png /usr/share/nginx/html/og-image.png
COPY robots.txt /usr/share/nginx/html/robots.txt
COPY sitemap.xml /usr/share/nginx/html/sitemap.xml
EXPOSE 8080
RUN sed -i 's/listen\s*80;/listen 8080;/' /etc/nginx/conf.d/default.conf
