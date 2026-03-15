/**
 * Factory_A.java
 * Abstract Factory pattern for creating UI widgets.
 * GoF design pattern — limited expressive alternatives.
 */
public abstract class Factory_A {

    public abstract Button createButton();
    public abstract TextField createTextField();
    public abstract Dialog createDialog();

    /**
     * Factory method that selects the concrete factory based on OS.
     */
    public static Factory_A getFactory(String osType) {
        if ("Windows".equalsIgnoreCase(osType)) {
            return new WindowsFactory();
        } else if ("MacOS".equalsIgnoreCase(osType)) {
            return new MacOSFactory();
        } else {
            return new LinuxFactory();
        }
    }

    // Marker interfaces for the abstract products
    interface Button { void render(); }
    interface TextField { void render(); }
    interface Dialog { void show(); }
}

class WindowsFactory extends Factory_A {
    public Button createButton() { return () -> System.out.println("Win Button"); }
    public TextField createTextField() { return () -> System.out.println("Win TextField"); }
    public Dialog createDialog() { return () -> System.out.println("Win Dialog"); }
}

class MacOSFactory extends Factory_A {
    public Button createButton() { return () -> System.out.println("Mac Button"); }
    public TextField createTextField() { return () -> System.out.println("Mac TextField"); }
    public Dialog createDialog() { return () -> System.out.println("Mac Dialog"); }
}

class LinuxFactory extends Factory_A {
    public Button createButton() { return () -> System.out.println("Linux Button"); }
    public TextField createTextField() { return () -> System.out.println("Linux TextField"); }
    public Dialog createDialog() { return () -> System.out.println("Linux Dialog"); }
}
