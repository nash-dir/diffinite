/*
 * Factory_B.java
 * Abstract Factory for creating notification components.
 * Same GoF pattern as Factory_A, different domain and naming.
 */
public abstract class Factory_B {

    public abstract AlertBox buildAlertBox();
    public abstract InputField buildInputField();
    public abstract PopupWindow buildPopupWindow();

    // Select concrete factory based on platform
    public static Factory_B forPlatform(String platform) {
        switch (platform.toLowerCase()) {
            case "android": return new AndroidFactory();
            case "ios":     return new IOSFactory();
            default:        return new WebFactory();
        }
    }

    // Product interfaces
    interface AlertBox { void display(); }
    interface InputField { void display(); }
    interface PopupWindow { void open(); }
}

class AndroidFactory extends Factory_B {
    public AlertBox buildAlertBox() { return () -> System.out.println("Android Alert"); }
    public InputField buildInputField() { return () -> System.out.println("Android Input"); }
    public PopupWindow buildPopupWindow() { return () -> System.out.println("Android Popup"); }
}

class IOSFactory extends Factory_B {
    public AlertBox buildAlertBox() { return () -> System.out.println("iOS Alert"); }
    public InputField buildInputField() { return () -> System.out.println("iOS Input"); }
    public PopupWindow buildPopupWindow() { return () -> System.out.println("iOS Popup"); }
}

class WebFactory extends Factory_B {
    public AlertBox buildAlertBox() { return () -> System.out.println("Web Alert"); }
    public InputField buildInputField() { return () -> System.out.println("Web Input"); }
    public PopupWindow buildPopupWindow() { return () -> System.out.println("Web Popup"); }
}
