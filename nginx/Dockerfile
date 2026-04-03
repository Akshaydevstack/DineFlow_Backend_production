FROM openresty/openresty:alpine-fat

RUN opm get SkyLothar/lua-resty-jwt

RUN sed -i 's/EVP_MD_CTX_create/EVP_MD_CTX_new/g' /usr/local/openresty/site/lualib/resty/evp.lua && \
    sed -i 's/EVP_MD_CTX_destroy/EVP_MD_CTX_free/g' /usr/local/openresty/site/lualib/resty/evp.lua

RUN mkdir -p /etc/nginx/jwt

EXPOSE 80

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;", "-c", "/etc/nginx/custom_nginx.conf"]