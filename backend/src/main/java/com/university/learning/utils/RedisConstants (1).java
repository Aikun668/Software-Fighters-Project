package com.university.learning.utils;

public class RedisConstants {

    public static final String LOGIN_CODE_KEY = "login:code:";
    public static final Long LOGIN_CODE_TTL = 2L;
    public static final String LOGIN_USER_KEY = "login:token:";
    public static final Long LOGIN_USER_TTL = 36000L;
    public static final String Register_CODE_KEY = "register:code:";
    public static final Long Register_CODE_TTL = 2L;
}
