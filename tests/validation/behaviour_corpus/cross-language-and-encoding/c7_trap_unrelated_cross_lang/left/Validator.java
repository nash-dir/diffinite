package org.example.signup;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Field validation for the account sign-up form.
 */
public class Validator {

    private static final Pattern EMAIL =
            Pattern.compile("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");
    private static final int MIN_PASSWORD = 12;

    private final List<String> errors = new ArrayList<>();

    public boolean validateEmail(String email) {
        if (email == null || email.trim().isEmpty()) {
            errors.add("email is required");
            return false;
        }
        if (!EMAIL.matcher(email.trim()).matches()) {
            errors.add("email is malformed");
            return false;
        }
        return true;
    }

    public boolean validatePassword(String password, String username) {
        if (password == null || password.length() < MIN_PASSWORD) {
            errors.add("password must be at least " + MIN_PASSWORD + " characters");
            return false;
        }
        boolean upper = false, lower = false, digit = false, symbol = false;
        for (char c : password.toCharArray()) {
            if (Character.isUpperCase(c)) upper = true;
            else if (Character.isLowerCase(c)) lower = true;
            else if (Character.isDigit(c)) digit = true;
            else symbol = true;
        }
        int classes = (upper ? 1 : 0) + (lower ? 1 : 0) + (digit ? 1 : 0) + (symbol ? 1 : 0);
        if (classes < 3) {
            errors.add("password needs three character classes");
            return false;
        }
        if (username != null && password.toLowerCase().contains(username.toLowerCase())) {
            errors.add("password must not contain the username");
            return false;
        }
        return true;
    }

    public boolean validatePhone(String phone) {
        String digits = phone == null ? "" : phone.replaceAll("[^0-9]", "");
        if (digits.length() < 9 || digits.length() > 11) {
            errors.add("phone number has wrong length");
            return false;
        }
        if (!digits.startsWith("0")) {
            errors.add("phone number must start with 0");
            return false;
        }
        return true;
    }

    public boolean validateAge(int birthYear, int currentYear) {
        int age = currentYear - birthYear;
        if (age < 14) {
            errors.add("guardian consent required under 14");
            return false;
        }
        if (age > 120) {
            errors.add("birth year looks wrong");
            return false;
        }
        return true;
    }

    public List<String> getErrors() {
        return new ArrayList<>(errors);
    }

    public void reset() {
        errors.clear();
    }
}
